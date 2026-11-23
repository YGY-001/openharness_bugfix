import logging
from typing import Any

from app.agent_state import BugFixState

logger = logging.getLogger(__name__)

MAX_REPLANS = 3


def analyze_failure(state: BugFixState) -> str:
    validation_result = state.get("validation_result") or {}
    fix_result = state.get("fix_result") or {}
    analysis_result = state.get("analysis_result") or {}

    if (
        state.get("test_passed") is False
        or validation_result.get("tests_failed", 0) > 0
    ):
        failed_tests = validation_result.get("failed_test_names") or []
        return f"test_failed: {failed_tests}"

    if fix_result.get("status") == "error":
        return f"patch_failed: {fix_result.get('error', 'unknown')}"

    if analysis_result.get("status") == "error":
        return f"analysis_failed: {analysis_result.get('error', 'unknown')}"

    return "unknown_failure"


async def replanner_node(state: BugFixState) -> dict[str, Any]:
    test_passed = state.get("test_passed")
    replan_count = state.get("replan_count", 0)

    logger.info(
        "Replanner checks result: test_passed=%s, replan_count=%s",
        test_passed,
        replan_count,
    )
    analysis_result = state.get("analysis_result") or {}

    if analysis_result.get("status") == "skipped":
        return {
            "done": True,
            "error": None,
        }

    if test_passed is True:
        return {
            "done": True,
            "error": None,
        }

    if replan_count >= MAX_REPLANS:
        return {
            "done": True,
            "error": "maximum_replans_exceeded",
        }

    failure_reason = analyze_failure(state)

    return {
        "done": False,
        "error": failure_reason,
        "replan_count": replan_count + 1,
    }


def should_replan(state: BugFixState) -> str:
    if state.get("done"):
        return "end"

    if state.get("error"):
        return "replan"

    return "end"