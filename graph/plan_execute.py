from langgraph.graph import END, START, StateGraph

from app.agent_state import BugFixState, create_initial_state
from app.executor import executor_node
from app.planner import planner_node
from app.replanner import replanner_node, should_replan


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


def build_bugfix_graph():
    """完整的 Planner → Executor → Replanner 控制流程。"""
    builder = StateGraph(BugFixState)

    builder.add_node("planner", planner_node)
    builder.add_node("executor", executor_node)
    builder.add_node("replanner", replanner_node)

    builder.add_edge(START, "planner")
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
) -> BugFixState:
    graph = build_bugfix_graph()

    initial_state = create_initial_state(
        code=code,
        language=language,
        test_case=test_case,
        description=description
    )

    return await graph.ainvoke(initial_state)