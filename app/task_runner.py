import logging
from app.task_store import TaskStore
from graph.plan_execute import run_planner_graph, run_bugfix_graph
from datetime import datetime

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
                "progress": 0.0,
            },
        )

        final_state = await run_bugfix_graph(
            code=task["code"],
            language=task["language"],
            test_case=task.get("test_case"),
        )
        analysis_result = final_state.get("analysis_result") or {}
        step_results = final_state.get("step_results", [])
        plan = final_state.get("plan", [])

        if analysis_result.get("status") == "skipped":
            final_status = "no_bugs_found"
        elif final_state.get("test_passed") is True:
            final_status = "completed"
        else:
            final_status = "failed"

        completed_steps = []
        failed_steps = []

        for step_result in step_results:
            plan_step = step_result.get("plan_step", "")
            step_status = step_result.get("status")

            if step_status == "success":
                if not (
                        step_result.get("step_type") == "validate"
                        and step_result.get("test_passed") is False
                ):
                    completed_steps.append(plan_step)

            if step_status in {"error", "not_implemented"} or (
                    step_result.get("step_type") == "validate"
                    and step_result.get("test_passed") is False
            ):
                failed_steps.append(plan_step)

        error = final_state.get("error")
        if final_status == "failed" and not error:
            error = "The workflow finished without a successful validation result."

        task_store.update(
            task_id,
            {
                "status": final_status,
                "progress": 1.0,
                "plan_title": "Bugfix Plan-Execute Workflow",
                "plan": plan,
                "current_step": final_state.get("current_step", 0),
                "total_steps": len(plan),
                "completed_steps": list(dict.fromkeys(completed_steps)),
                "failed_steps": list(dict.fromkeys(failed_steps)),
                "review_result": final_state.get("review_result"),
                "analysis_result": final_state.get("analysis_result"),
                "fix_result": final_state.get("fix_result"),
                "validation_result": final_state.get("validation_result"),
                "patch": final_state.get("patch"),
                "fixed_code": final_state.get("fixed_code"),
                "error": error,
                "completed_at": datetime.now().isoformat(),
            },
        )
    except Exception as exc:
        logger.exception("Planner failed for task %s", task_id)

        task_store.update(
            task_id,
            {
                "status": "failed",
                "progress": 1.0,
                "error": str(exc),
                "failed_steps": ["bugfix_workflow"],
                "completed_at": datetime.now().isoformat(),
            },
        )