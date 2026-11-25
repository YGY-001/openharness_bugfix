from langgraph.graph import END, START, StateGraph

from app.agent_state import BugFixState, create_initial_state
from app.executor import executor_node
from app.planner import planner_node
from app.replanner import replanner_node, should_replan
from app.task_persistence import TaskPersistence
from typing import Any
from collections.abc import Awaitable, Callable

StateProgressCallback = Callable[[BugFixState], Awaitable[None]]

def resume_entry(state: BugFixState) -> str:
    last_node = state.get("last_node")

    if last_node == "planner":
        return "executor"

    if last_node == "executor":
        if should_continue_executing(state) == "continue":
            return "executor"
        return "replanner"

    if last_node == "replanner":
        if should_replan(state) == "replan":
            return "planner"
        return "end"

    # 新任务没有 last_node，从 Planner 开始。
    return "planner"

def should_continue_executing(state: BugFixState) -> str:
    if state.get("error"):
        return "done"

    current_step = state.get("current_step", 0)
    plan = state.get("plan", [])

    if current_step < len(plan):
        return "continue"

    return "done"


def build_planner_graph():
    """只运行 Planner，供当前 API 阶段使用。"""
    builder = StateGraph(BugFixState)

    builder.add_node("planner", planner_node)
    builder.add_edge(START, "planner")
    builder.add_edge("planner", END)

    return builder.compile()

async def planner_checkpoint_node(
    state: BugFixState,
) -> dict[str, Any]:
    updates = await planner_node(state)
    return {**updates, "last_node": "planner"}


async def executor_checkpoint_node(
    state: BugFixState,
) -> dict[str, Any]:
    updates = await executor_node(state)
    return {**updates, "last_node": "executor"}


async def replanner_checkpoint_node(
    state: BugFixState,
) -> dict[str, Any]:
    updates = await replanner_node(state)
    return {**updates, "last_node": "replanner"}

def build_bugfix_graph():
    """完整的 Planner → Executor → Replanner 控制流程。"""
    builder = StateGraph(BugFixState)

    builder.add_node("planner", planner_checkpoint_node)
    builder.add_node("executor", executor_checkpoint_node)
    builder.add_node("replanner", replanner_checkpoint_node)

    builder.add_conditional_edges(
        START,
        resume_entry,
        {
            "planner": "planner",
            "executor": "executor",
            "replanner": "replanner",
            "end": END,
        },
    )
    builder.add_edge("planner", "executor")

    builder.add_conditional_edges(
        "executor",
        should_continue_executing,
        {
            "continue": "executor",
            "done": "replanner",
        },
    )

    builder.add_conditional_edges(
        "replanner",
        should_replan,
        {
            "replan": "planner",
            "end": END,
        },
    )

    return builder.compile()


async def run_planner_graph(
    code: str,
    language: str = "java",
    test_case: str | None = None,
    description: str | None = None,
) -> BugFixState:
    graph = build_planner_graph()

    initial_state = create_initial_state(
        code=code,
        language=language,
        test_case=test_case,
        description=description
    )

    return await graph.ainvoke(initial_state)


async def run_bugfix_graph(
    code: str,
    language: str = "java",
    test_case: str | None = None,
    description: str | None = None,
    session_id: str | None = None,
    task_persistence: TaskPersistence | None = None,
    resume_state: BugFixState | None = None,
    on_state: StateProgressCallback | None = None,
) -> BugFixState:
    graph = build_bugfix_graph()

    if resume_state is not None:
        initial_state = resume_state
    else:
        initial_state = create_initial_state(
            code=code,
            language=language,
            test_case=test_case,
            description=description,
        )
    final_state = initial_state

    #边执行langgraph 边保存运行状态
    async for state in graph.astream(
            initial_state,
            stream_mode="values",
    ):
        final_state = state

        if task_persistence is not None and session_id is not None:
            await task_persistence.save_agent_state(
                session_id=session_id,
                state=state,
            )
        if on_state is not None:
            await on_state(state)

    return final_state