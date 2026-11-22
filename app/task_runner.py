import logging
from app.task_store import TaskStore
from graph.plan_execute import run_planner_graph

logger = logging.getLogger(__name__)


async def run_bugfix_task(task_store: TaskStore, task_id: str) -> None:
    task = task_store.get(task_id)
    if task is None:
        logger.error("Task %s was not found before background execution", task_id)
        return
    try:
        task_store.update(
            task_id,
            {
                "status": "running",
                "progress": 0.05,
            },
        )

        final_state = await run_planner_graph(
            code=task["code"],
            language=task["language"],
            test_case=task.get("test_case"),
        )
        plan = final_state["plan"]

        task_store.update(
            task_id,
            {
                "status": "planned",
                "progress": 0.0,
                "plan_title": "Bugfix Plan-Execute Workflow",
                "current_step": 0,
                "total_steps": len(plan),
                "plan": plan,
            },
        )
    except Exception as exc:
        logger.exception("Planner failed for task %s", task_id)

        task_store.update(
            task_id,
            {
                "status": "failed",
                "error": str(exc),
                "failed_steps": ["planner"],
            },
        )