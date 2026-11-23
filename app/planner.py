import json
import logging
import re
from typing import Any

from app.agent_state import BugFixState
from app.llm_client import call_llm

logger = logging.getLogger(__name__)

AGENT_TRIGGERS = {
    "review": ("审查", "review", "检查", "check", "检测", "detect", "漏洞", "vulnerability"),
    "analyze": ("分析", "analyze", "根因", "root cause", "影响", "impact", "复杂", "complex"),
    "fix": ("修复", "fix", "补丁", "patch", "修", "correct"),
    "validate": ("验证", "validate", "测试", "test", "确认", "verify"),
}

ALL_AGENTS_KEYWORDS = ("全面", "完整", "全部", "所有", "all", "full", "complete")

PLAN_STEPS = [
    ("review", "step_1_review: 使用 Reviewer 审查代码，识别潜在 Bug"),
    ("analyze", "step_2_analyze: 使用 Analyzer 分析 Bug 根因"),
    ("fix", "step_3_fix: 使用 Fixer 生成修复补丁"),
    ("validate", "step_4_validate: 使用 Validator 验证修复结果"),
]
def _select_agents_by_keywords(
    description: str | None,
) -> set[str] | None:
    description_lower = (description or "").lower()

    if any(keyword in description_lower for keyword in ALL_AGENTS_KEYWORDS):
        return set(AGENT_TRIGGERS)

    triggered = {
        agent_type
        for agent_type, keywords in AGENT_TRIGGERS.items()
        if any(keyword.lower() in description_lower for keyword in keywords)
    }

    return triggered or None
def _complete_agent_dependencies(triggered: set[str]) -> set[str]:
    selected = set(triggered)

    # 验证需要修复；修复需要分析和审查；分析需要审查。
    if "validate" in selected:
        selected.add("fix")
    if "fix" in selected:
        selected.update({"analyze", "validate"})
    if "analyze" in selected:
        selected.add("review")
    return selected
def _build_plan(code: str, selected: set[str]) -> list[str]:
    plan = [
        step_text
        for agent_type, step_text in PLAN_STEPS
        if agent_type in selected
    ]

    if len(code) > 500:
        plan.insert(0, "step_0_preprocess: 预处理较长代码，提取关键内容")

    return plan

# 无大模型的规划
def generate_initial_plan(
    code: str,
    language: str,
    description: str | None = None,
) -> list[str]:
    selected = _select_agents_by_keywords(description)

    #  没有关键词时沿用完整修复流程。
    if selected is None:
        selected = set(AGENT_TRIGGERS)

    selected = _complete_agent_dependencies(selected)
    return _build_plan(code, selected)

async def _classify_agents_with_llm(
    code: str,
    language: str,
    description: str | None,
) -> set[str]:
    prompt = f"""根据用户任务，判断需要哪些 Agent。

    可选 Agent 类型：
    - review：审查代码，查找 Bug
    - analyze：分析 Bug 根因
    - fix：生成修复方案
    - validate：验证修复结果
    
    编程语言：{language}
    用户描述：{description or "无描述"}
    代码片段：
    ```{language}
    {code[:500]}
    ```
    请只返回 JSON 字符串数组，例如：
    ["review", "analyze", "fix", "validate"]
    """
    content = await call_llm(
        prompt,
        max_tokens=200,
        temperature=0.0,
    )

    match = re.search(r"\[[\s\S]*]", content)
    if not match:
        raise ValueError("Planner response did not contain a JSON array.")

    result = json.loads(match.group(0))
    if not isinstance(result, list):
        raise ValueError("Planner response must be a JSON array.")

    selected = {
        item
        for item in result
        if isinstance(item, str) and item in AGENT_TRIGGERS
    }

    if not selected:
        raise ValueError("Planner response did not select a valid Agent.")

    return selected

# 大模型规划
async def generate_plan_with_fallback(
    code: str,
    language: str,
    description: str | None,
) -> list[str]:
    selected = _select_agents_by_keywords(description)
    # 命中关键词时直接规划，不额外请求模型。
    if selected is not None:
        logger.info("Planner selected agents using description keywords.")
        return _build_plan(code, _complete_agent_dependencies(selected))

    # 没命中关键词才让模型分类。
    try:
        selected = await _classify_agents_with_llm(
            code=code,
            language=language,
            description=description,
        )
        return _build_plan(code, _complete_agent_dependencies(selected))
    except Exception as exc:
        logger.warning(
            "LLM planning failed; falling back to the full plan: %s",
            exc,
        )
        return generate_initial_plan(code, language, description)

# 重规划时不调用大模型规划，避免额外请求模型，LLM出错回退到四步计划
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
        description=state.get("description"),
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
        plan = await generate_plan_with_fallback(
            code=state["code"],
            language=state["language"],
            description=state.get("description"),
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