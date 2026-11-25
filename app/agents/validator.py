import json
from typing import Any

from app.agent_state import BugFixState
from app.llm_client import call_llm


def parse_validation_response(content: str) -> dict[str, Any]:
    start = content.find("{")
    end = content.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise ValueError("Validator response does not contain a JSON object.")

    try:
        result = json.loads(content[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("Validator returned invalid JSON.") from exc

    if not isinstance(result, dict):
        raise ValueError("Validator response must be a JSON object.")

    if not isinstance(result.get("test_passed"), bool):
        raise ValueError("'test_passed' must be a boolean.")

    if not isinstance(result.get("validation_reason"), str):
        raise ValueError("'validation_reason' must be a string.")

    side_effects = result.get("potential_side_effects", [])
    if not isinstance(side_effects, list):
        raise ValueError("'potential_side_effects' must be a list.")
    if any(not isinstance(item, str) for item in side_effects):
        raise ValueError("Each potential side effect must be a string.")

    if not isinstance(result.get("additional_tests_needed"), bool):
        raise ValueError("'additional_tests_needed' must be a boolean.")

    return result


async def validator_handler(state: BugFixState) -> dict[str, Any]:
    analysis_result = state.get("analysis_result") or {}
    fix_result = state.get("fix_result") or {}

    if (
        analysis_result.get("status") == "skipped"
        or fix_result.get("status") == "skipped"
    ):
        return {
            "status": "skipped",
            "test_passed": None,
            "validation_reason": "Validation skipped because no confirmed bug was fixed.",
            "potential_side_effects": [],
            "additional_tests_needed": False,
            "validation_mode": "not_applicable",
        }

    fixed_code = fix_result.get("fixed_code")
    if not isinstance(fixed_code, str) or not fixed_code.strip():
        raise ValueError("Fixer did not provide fixed_code.")

    test_case = state.get("test_case") or "No test case provided."

    prompt = f"""You are a code validation agent.

    Compare the original code with the proposed fixed code and analysis.
    If a test case is provided, reason about whether the fixed code should satisfy it.
    
    This is static review only. You have not executed the code or test case.
    Set test_passed to true only if the fix appears logically correct.
    Do not claim that tests were actually run.
    
    Return exactly one JSON object with:
    - test_passed: a boolean static assessment.
    - validation_reason: explain your assessment and whether execution occurred.
    - potential_side_effects: a list of possible side effects.
    - additional_tests_needed: a boolean.
    
    Language: {state["language"]}
    
    Original code:
    ```{state["language"]}
    {state["code"]}
    ```
    Fixed code:
    {fixed_code}
    Patch:
    {fix_result.get("patch", "")}
    
    Analysis:
    {json.dumps(analysis_result, ensure_ascii=False)}
    
    Test case:
    {test_case}
    """
    content = await call_llm(
        prompt,
        max_tokens=2000,
        temperature=0.1,
        thinking=False,
    )
    result = parse_validation_response(content)

    return {
        "status": "success",
        **result,
        "validation_mode": "llm_static_review",
    }