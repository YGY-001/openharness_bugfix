import operator
from typing import Annotated, Any, TypedDict


class BugFixState(TypedDict):
    # 输入
    code: str
    language: str
    test_case: str | None

    # 计划
    plan: list[str]
    current_step: int

    # 各执行节点返回的结果
    step_results: Annotated[list[dict[str, Any]], operator.add]

    # 各 Agent 的输出
    review_result: dict[str, Any] | None
    analysis_result: dict[str, Any] | None
    fix_result: dict[str, Any] | None
    validation_result: dict[str, Any] | None

    # 最终结果
    bug_location: str | None
    bug_type: str | None
    patch: str | None
    fixed_code: str | None
    test_passed: bool | None

    # 流程控制
    replan_count: int
    error: str | None
    done: bool

def create_initial_state(
    code: str,
    language: str = "java",
    test_case: str | None = None,
) -> BugFixState:
    return {
        "code": code,
        "language": language,
        "test_case": test_case,
        "plan": [],
        "current_step": 0,
        "step_results": [],
        "review_result": None,
        "analysis_result": None,
        "fix_result": None,
        "validation_result": None,
        "bug_location": None,
        "bug_type": None,
        "patch": None,
        "fixed_code": None,
        "test_passed": None,
        "replan_count": 0,
        "error": None,
        "done": False,
    }