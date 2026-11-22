from pydantic import BaseModel,Field
from typing import Any

class BugSubmitRequest(BaseModel):
    code: str
    language: str = "java"
    description: str | None = None
    file_path: str | None = None
    severity: str = "MEDIUM"
    test_case: str | None = None


class BugSubmitAccepted(BaseModel):
    status: str
    task_id: str
    session_id: str
    message: str


class BugTaskResponse(BaseModel):
    task_id: str
    session_id: str
    status: str
    progress: float = 0.0
    plan_title: str | None = None
    plan: list[str] = Field(default_factory=list)
    current_step: int | None = None
    total_steps: int | None = None
    completed_steps: list[str] = Field(default_factory=list)
    failed_steps: list[str] = Field(default_factory=list)
    review_result: dict[str, Any] | None = None
    analysis_result: dict[str, Any] | None = None
    fix_result: dict[str, Any] | None = None
    validation_result: dict[str, Any] | None = None
    patch: str | None = None
    fixed_code: str | None = None
    error: str | None = None
    created_at: str | None = None
    completed_at: str | None = None
    approval_required: bool = False
    approval_id: str | None = None
    data_request_id: str | None = None
    data_question: str | None = None
