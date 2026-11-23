import json
from typing import Any

from app.agent_state import BugFixState
from app.llm_client import call_llm


def parse_analysis_response(content: str) -> dict[str, Any]:
    start = content.find("{")
    end = content.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise ValueError("Analyzer response does not contain a JSON object.")

    try:
        result = json.loads(content[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("Analyzer returned invalid JSON.") from exc

    if not isinstance(result, dict):
        raise ValueError("Analyzer response must be a JSON object.")

    for field in ("confirmed_bugs", "false_positives"):
        value = result.get(field, [])
        if not isinstance(value, list):
            raise ValueError(f"'{field}' must be a list.")
        if any(not isinstance(item, dict) for item in value):
            raise ValueError(f"Each item in '{field}' must be a JSON object.")

    text_fields = (
        "bug_location",
        "bug_type",
        "root_cause",
        "fix_suggestion",
        "fix_strategy",
    )

    for field in text_fields:
        value = result.get(field, "")
        if not isinstance(value, str):
            raise ValueError(f"'{field}' must be a string.")
        result[field] = value

    confidence = result.get("confidence", 0.0)
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("'confidence' must be a number.")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("'confidence' must be between 0 and 1.")

    result["confirmed_bugs"] = result.get("confirmed_bugs", [])
    result["false_positives"] = result.get("false_positives", [])

    return result


async def analyzer_handler(state: BugFixState) -> dict[str, Any]:
    review_result = state.get("review_result") or {}
    bug_candidates = review_result.get("bug_candidates", [])

    if not bug_candidates:
        return {
            "status": "skipped",
            "confirmed_bugs": [],
            "false_positives": [],
            "bug_location": "",
            "bug_type": "none",
            "root_cause": "",
            "confidence": 0.0,
            "fix_suggestion": "",
            "fix_strategy": "No candidate bugs to analyze.",
        }

    bug_info = json.dumps(bug_candidates, ensure_ascii=False)

    prompt = f"""You are a bug root-cause analysis agent.
    
    Review the code and the candidate issues found by another reviewer.
    Treat those candidates as hypotheses: verify whether they are real bugs,
    and identify false positives.
    
    Return exactly one JSON object with:
    - confirmed_bugs: a list of real bugs, each with location, type,
      root_cause, impact_scope, and recommended_fix.
    - false_positives: a list of rejected candidates, each with location
      and reason.
    - bug_location: the main confirmed bug location, or an empty string.
    - bug_type: the main bug type, or "none".
    - root_cause: the main root cause, or an empty string.
    - confidence: a number from 0.0 to 1.0.
    - fix_suggestion: a concise suggested change.
    - fix_strategy: the recommended repair strategy.
    
    If none of the candidates is a real bug, use an empty confirmed_bugs list.
    Do not wrap the JSON in Markdown fences.
    
    Language: {state["language"]}
    
    Original code:
    ```{state["language"]}
    {state["code"]}
    ```
    Reviewer candidates:
    {bug_info}
        
    """

    content = await call_llm(
        prompt,
        max_tokens=2500,
        temperature=0.2,
    )
    result = parse_analysis_response(content)

    return {
        "status": "success",
        **result,
    }

