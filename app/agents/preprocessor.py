from typing import Any

from app.agent_state import BugFixState


async def preprocess_handler(state: BugFixState) -> dict[str, Any]:
    return {
        "status": "skipped",
        "reason": (
            "Code context compression is not implemented yet; "
            "the original source will be passed to the agents."
        ),
    }