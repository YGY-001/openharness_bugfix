import logging
from app.task_store import TaskStore
from graph.plan_execute import run_planner_graph, run_bugfix_graph
from datetime import datetime
from app.task_persistence import TaskPersistence
from typing import Any

logger = logging.getLogger(__name__)
task_persistence = TaskPersistence()
# 当前活跃的task 避免同一会话重复排入后台
_active_task_ids: set[str] = set()


def reserve_task(task_id: str) -> bool:
    if task_id in _active_task_ids:
        return False

    _active_task_ids.add(task_id)
    return True


def release_task(task_id: str) -> None:
    _active_task_ids.discard(task_id)

async def run_bugfix_task(
    task_store: TaskStore,
    task_id: str,
    resume_state: dict[str, Any] | None = None,
    task_reserved: bool = False,
) -> None:
    if not task_reserved and not reserve_task(task_id):
        logger.warning("Task %s is already running; duplicate run ignored", task_id)
        return

    try:
        await _run_bugfix_task_body(
            task_store,
            task_id,
            resume_state,
        )
    finally:
        release_task(task_id)

async def _run_bugfix_task_body(task_store: TaskStore, task_id: str, resume_state:dict[str,Any] | None = None) -> None:
    task = task_store.get(task_id)
    if task is None:
        logger.error("Task %s was not found before background execution", task_id)
        return
    try:
        resume_progress = 0.0
        if resume_state is not None:
            total_steps = len(resume_state.get("plan", []))
            if total_steps:
                resume_progress = min(
                    resume_state.get("current_step", 0) / total_steps,
                    1.0,
                )

        task_store.update(
            task_id,
            {
                "status": "running",
                "progress": resume_progress,
            },
        )

        final_state = await run_bugfix_graph(
            code=task["code"],
            language=task["language"],
            test_case=task.get("test_case"),
            description=task.get("description"),
            session_id=task["session_id"],
            task_persistence=task_persistence,
            resume_state=resume_state,
        )
        analysis_result = final_state.get("analysis_result") or {}
        step_results = final_state.get("step_results", [])
        plan = final_state.get("plan", [])

        validation_planned = any(
            result.get("step_type") == "validate"
            for result in step_results
        )

        has_step_failure = any(
            result.get("status") in {"error", "not_implemented"}
            or (
                    result.get("step_type") == "validate"
                    and result.get("test_passed") is False
            )
            for result in step_results
        )

        no_confirmed_bugs = (
                analysis_result.get("status") == "skipped"
                or (
                        analysis_result.get("status") == "success"
                        and not analysis_result.get("confirmed_bugs", [])
                )
        )

        if (
                no_confirmed_bugs
                and not final_state.get("error")
                and not has_step_failure
        ):
            final_status = "no_bugs_found"
        elif final_state.get("error") or has_step_failure:
            final_status = "failed"
        elif validation_planned and final_state.get("test_passed") is not True:
            final_status = "failed"
        else:
            final_status = "completed"

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