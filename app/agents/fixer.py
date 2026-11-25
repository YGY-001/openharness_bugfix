import json
from typing import Any

from app.agent_state import BugFixState
from app.llm_client import call_llm


def parse_fix_response(content: str) -> dict[str, Any]:
    start = content.find("{")
    end = content.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise ValueError("Fixer response does not contain a JSON object.")

    try:
        result = json.loads(content[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("Fixer returned invalid JSON.") from exc

    if not isinstance(result, dict):
        raise ValueError("Fixer response must be a JSON object.")

    for field in ("patch", "fixed_code", "fix_explanation"):
        value = result.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"'{field}' must be a non-empty string.")

    return result


async def fixer_handler(state: BugFixState) -> dict[str, Any]:
    analysis_result = state.get("analysis_result") or {}
    confirmed_bugs = analysis_result.get("confirmed_bugs", [])

    if analysis_result.get("status") == "skipped" or not confirmed_bugs:
        return {
            "status": "skipped",
            "patch": "",
            "fixed_code": state["code"],
            "fix_explanation": "No confirmed bugs to fix.",
        }

    analysis_info = json.dumps(analysis_result, ensure_ascii=False)

    prompt = f"""You are a careful code-fixing agent.

    Use the confirmed root-cause analysis to make the smallest safe change.
    Return exactly one JSON object with:
    - patch: a unified diff showing the changes.
    - fixed_code: the complete corrected source file, without Markdown fences.
    - fix_explanation: a concise explanation of the change.
    
    Do not invent unrelated changes. Preserve the language and style of the source.
    
    Language: {state["language"]}
    
    Original source:
    ```{state["language"]}
    {state["code"]}
    ```
    Analyzer result:
    {analysis_info}
    """
    content = await call_llm(
        prompt,
        max_tokens=4000,
        temperature=0.2,
        thinking=False,
    )
    result = parse_fix_response(content)

    return {
        "status": "success",
        "patch": result["patch"],
        "fixed_code": result["fixed_code"],
        "fix_explanation": result["fix_explanation"],
    }