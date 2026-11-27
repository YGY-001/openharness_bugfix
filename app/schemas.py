from pydantic import BaseModel,Field
from typing import Any


#会话恢复
class ResumeRequest(BaseModel):
    session_id: str

# bug请求接受
class BugSubmitRequest(BaseModel):
    code: str
    language: str = "java"
    description: str | None = None
    file_path: str | None = None
    severity: str = "MEDIUM"
    test_case: str | None = None

# bug请求返回
class BugSubmitAccepted(BaseModel):
    status: str
    task_id: str
    session_id: str
    message: str

# bug回复
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


# bug task列表返回
class BugTaskListResponse(BaseModel):
    tasks: list[BugTaskResponse] = Field(default_factory=list)
    total: int = 0

# 查询自己可恢复的会话
class SessionSummary(BaseModel):
    session_id: str
    task_id: str
    status: str
    progress: float = 0.0
    current_step: int | None = None
    total_steps: int | None = None
    created_at: str | None = None
    resumable: bool = False


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary] = Field(default_factory=list)
    total: int = 0

# 注册
class UserRegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    email: str | None = None

class UserRegisterResponse(BaseModel):
    status: str
    username: str
#登录
class UserLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)

class UserLoginResponse(BaseModel):
    status: str
    username: str
    token: str

#统计用户任务
class TaskCounts(BaseModel):
    total: int = 0
    pending: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    no_bugs_found: int = 0

class TaskStatsResponse(BaseModel):
    tasks: TaskCounts