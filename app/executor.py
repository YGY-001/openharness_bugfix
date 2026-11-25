import logging
from collections.abc import Awaitable, Callable
from typing import Any
from app.agent_state import BugFixState
from app.agents.reviewer import reviewer_handler
from app.agents.analyzer import analyzer_handler
from app.agents.fixer import fixer_handler
from app.agents.validator import validator_handler
from app.agents.preprocessor import preprocess_handler

logger = logging.getLogger(__name__)

StepHandler = Callable[[BugFixState], Awaitable[dict[str, Any]]]

STEP_HANDLERS: dict[str, StepHandler] = {
    "preprocess": preprocess_handler,
    "review": reviewer_handler,
    "analyze": analyzer_handler,
    "fix":fixer_handler,
    "validate":validator_handler
}


def parse_step_type(plan_step: str) -> str:
    text = plan_step.lower()

    if "preprocess" in text:
        return "preprocess"
    if "review" in text:
        return "review"
    if "analyze" in text or "analysis" in text:
        return "analyze"
    if "fix" in text or "patch" in text:
        return "fix"
    if "validate" in text or "test" in text:
        return "validate"

    return "unknown"


async def executor_node(state: BugFixState) -> dict[str, Any]:
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)

    if current_step >= len(plan):
        return {"done": True}

    current_plan = plan[current_step]
    step_type = parse_step_type(current_plan)

    logger.info(
        "Executor step %s/%s: %s",
        current_step + 1,
        len(plan),
        current_plan,
    )

    handler = STEP_HANDLERS.get(step_type)

    if handler is None:
        result = {
            "status": "not_implemented",
            "error": f"No handler registered for step type: {step_type}",
        }
    else:
        try:
            result = await handler(state)
        except Exception as exc:
            logger.exception("Executor step failed: %s", current_plan)
            result = {
                "status": "error",
                "error": str(exc),
            }

    updates: dict[str, Any] = {
        "current_step": current_step + 1,
        "step_results": [
            {
                "plan_step": current_plan,
                "step_type": step_type,
                "plan_attempt": state.get("replan_count", 0),
                **result,
            }
        ],
    }

    if result.get("status") in {"error", "not_implemented"}:
        updates["error"] = result.get("error", "executor_step_failed")

    if step_type == "review":
        updates["review_result"] = result
    elif step_type == "analyze":
        updates["analysis_result"] = result
        updates["bug_location"] = result.get("bug_location")
        updates["bug_type"] = result.get("bug_type")
    elif step_type == "fix":
        updates["fix_result"] = result
        updates["patch"] = result.get("patch")
        updates["fixed_code"] = result.get("fixed_code")
    elif step_type == "validate":
        updates["validation_result"] = result
        updates["test_passed"] = result.get("test_passed")

    return updates