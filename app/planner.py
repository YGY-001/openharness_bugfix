import logging
from typing import Any

from app.agent_state import BugFixState

logger = logging.getLogger(__name__)


def generate_initial_plan(code: str, language: str) -> list[str]:
    plan = [
        "step_1_review: 使用 Reviewer 审查代码，识别潜在 Bug",
        "step_2_analyze: 使用 Analyzer 分析 Bug 根因",
        "step_3_fix: 使用 Fixer 生成修复补丁",
        "step_4_validate: 使用 Validator 验证修复结果",
    ]

    if len(code) > 500:
        plan.insert(
            0,
            "step_0_preprocess: 预处理较长代码，提取关键内容",
        )

    return plan


def generate_replan(state: BugFixState) -> list[str]:
    error = state.get("error") or ""

    if "test_failed" in error:
        return [
            "step_1_reanalyze: 重新分析 Bug 和测试失败原因",
            "step_2_refix: 生成新的修复补丁",
            "step_3_validate: 再次验证修复结果",
        ]

    if "patch_failed" in error:
        return [
            "step_1_analyze_patch: 分析补丁失败原因",
            "step_2_generate_new_patch: 生成新的补丁",
            "step_3_validate: 验证新补丁",
        ]

    return generate_initial_plan(
        code=state.get("code", ""),
        language=state.get("language", "java"),
    )


async def planner_node(state: BugFixState) -> dict[str, Any]:
    replan_count = state.get("replan_count", 0)

    logger.info(
        "Planner starts planning; replan_count=%s",
        replan_count,
    )

    if state.get("error") and replan_count > 0:
        plan = generate_replan(state)
    else:
        plan = generate_initial_plan(
            code=state["code"],
            language=state["language"],
        )

    logger.info("Planner generated plan: %s", plan)

    return {
        "plan": plan,
        "current_step": 0,
        "step_results": [],
        "error": None,
        "test_passed": None,
        "done": False,
    }