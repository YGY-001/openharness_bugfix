import json
from typing import Any

from app.agent_state import BugFixState
from app.llm_client import call_llm


def parse_review_response(content: str) -> dict[str, Any]:
    start = content.find("{")
    end = content.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise ValueError("Reviewer response does not contain a JSON object.")

    try:
        result = json.loads(content[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("Reviewer returned invalid JSON.") from exc

    if not isinstance(result, dict):
        raise ValueError("Reviewer response must be a JSON object.")

    bug_candidates = result.get("bug_candidates", [])
    potential_issues = result.get("potential_issues", [])

    if not isinstance(bug_candidates, list):
        raise ValueError("'bug_candidates' must be a list.")

    if not isinstance(potential_issues, list):
        raise ValueError("'potential_issues' must be a list.")

    if any(not isinstance(item, dict) for item in bug_candidates):
        raise ValueError("Each bug candidate must be a JSON object.")

    return result


async def reviewer_handler(state: BugFixState) -> dict[str, Any]:
    code = state["code"]
    language = state["language"]

    prompt = f"""You are a senior code review agent.
    Review the following {language} code for likely bugs.
    
    Return exactly one JSON object with these fields:
    - bug_candidates: a list of objects. Each object should include location, type,
      severity, description, and confidence.
    - potential_issues: a list of additional concerns.
    - code_quality: a short quality rating.
    - summary: a concise review summary.
    
    If you find no likely bugs, return an empty bug_candidates list.
    Do not wrap the JSON in Markdown fences.
    
    Code:
    ```{language}
    {code}
    ```
    """

    content = await call_llm(
        prompt,
        max_tokens=2000,
        temperature=0.2,
        thinking=False,
    )
    result = parse_review_response(content)

    return {
        "status": "success",
        "bug_candidates": result.get("bug_candidates", []),
        "potential_issues": result.get("potential_issues", []),
        "code_quality": result.get("code_quality", "unknown"),
        "summary": result.get("summary", ""),
    }