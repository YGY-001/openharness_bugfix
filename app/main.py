from datetime import datetime
from uuid import uuid4
from fastapi import FastAPI, HTTPException, BackgroundTasks,Query,Depends
from app.schemas import (
    BugSubmitRequest, BugSubmitAccepted, BugTaskResponse, ResumeRequest, BugTaskListResponse,
    UserRegisterRequest, UserRegisterResponse, UserLoginRequest, UserLoginResponse, SessionListResponse,
    TaskStatsResponse
)
from app.auth_security import hash_password, verify_password, create_access_token
from app.task_store import TaskStore
from app.task_runner import run_bugfix_task,task_persistence,reserve_task
from app.user_store import UserStore
from app.auth_dependencies import get_current_user

app = FastAPI(title="Bugfix Agent")
task_store = TaskStore()
user_store = UserStore()

@app.get("/api/health")
async def health():
    return {"status": "ok"}
@app.post(
    "/api/register",
    response_model=UserRegisterResponse,
    status_code=201,
)
def register(user: UserRegisterRequest):
    password_hash = hash_password(user.password)

    created = user_store.create_user(
        username=user.username,
        password_hash=password_hash,
        email=user.email,
    )

    if not created:
        raise HTTPException(
            status_code=409,
            detail="Username already exists",
        )

    return {
        "status": "registered",
        "username": user.username,
    }
@app.post("/api/login", response_model=UserLoginResponse)
def login(user: UserLoginRequest):
    stored_user = user_store.get_user(user.username)

    if (
        stored_user is None
        or not verify_password(
            user.password,
            stored_user["password_hash"],
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    token = create_access_token(user.username)

    return {
        "status": "success",
        "username": user.username,
        "token": token,
    }

@app.get("/api/bug/tasks", response_model=BugTaskListResponse)
async def list_bug_tasks(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    username: str = Depends(get_current_user),
):
    return task_store.list_tasks(
        username=username,
        status=status,
        limit=limit,
    )

@app.post("/api/bug/submit", response_model=BugSubmitAccepted)
async def submit_bug(
        bug: BugSubmitRequest,background_tasks:BackgroundTasks,username:str = Depends(get_current_user)):
    now = datetime.now()
    task_id = f"task_{now:%Y%m%d%H%M%S}_{uuid4().hex[:6]}"
    session_id = f"session-{task_id}"

    task = {
        "username":username,
        "task_id": task_id,
        "session_id": session_id,
        "status": "pending",
        "progress": 0.0,
        "completed_steps": [],
        "failed_steps": [],
        "created_at": now.isoformat(),
        "approval_required": False,
        "code": bug.code,
        "language": bug.language,
        "description": bug.description or "",
        "file_path": bug.file_path or "",
        "severity": bug.severity,
        "test_case": bug.test_case,
    }
    task_store.save(task_id, task)

    # fastapi的后台函数，把 run_bugfix_task 和它需要的两个参数登记起来，之后再调用
    background_tasks.add_task(
        run_bugfix_task,
        task_store,
        task_id,
    )
    return BugSubmitAccepted(
        status="submitted",
        task_id=task_id,
        session_id=session_id,
        message=f"Task submitted. Poll GET /api/bug/task/{task_id} for results.",
    )

@app.get("/api/bug/task/{task_id}", response_model=BugTaskResponse)
async def get_bug_task(task_id: str,username: str = Depends(get_current_user), ):
    task = task_store.get(task_id)
    if task is None or task.get("username") != username:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.post("/api/session/resume")
async def resume_session(request: ResumeRequest,background_tasks:BackgroundTasks,
                         username:str = Depends(get_current_user),):
    snapshot = await task_persistence.load_agent_state(request.session_id)

    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail="Session snapshot not found",
        )

    state = snapshot.get("state") or {}

    if "last_node" not in state:
        raise HTTPException(
            status_code=409,
            detail="Snapshot does not contain a resume checkpoint",
        )

    prefix = "session-"
    if not request.session_id.startswith(prefix):
        raise HTTPException(
            status_code=400,
            detail="Invalid session_id",
        )

    task_id = request.session_id.removeprefix(prefix)
    task = task_store.get(task_id)

    if task is not None and task.get("username") != username:
        raise HTTPException(
            status_code=404,
            detail="Session snapshot not found",
        )

    if task is None and state.get("username") != username:
        raise HTTPException(
            status_code=404,
            detail="Session snapshot not found",
        )

    if state.get("username") not in (None, username):
        raise HTTPException(
            status_code=404,
            detail="Session snapshot not found",
        )

    # 旧快照可能没有 username；确认任务所有者后补入，供后续保存。
    state["username"] = username

    if state.get("done"):
        return {
            "status": "already_completed",
            "resumable": False,
            "session_id": request.session_id,
        }

    if task is None:
        code = state.get("code")
        if not isinstance(code, str):
            raise HTTPException(
                status_code=404,
                detail="Original task data is unavailable",
            )

        task = {
            "task_id": task_id,
            "session_id": request.session_id,
            "username": username,
            "status": "pending",
            "progress": 0.0,
            "completed_steps": [],
            "failed_steps": [],
            "created_at": snapshot.get("saved_at"),
            "approval_required": False,
            "code": code,
            "language": state.get("language", "java"),
            "description": state.get("description") or "",
            "file_path": "",
            "severity": "MEDIUM",
            "test_case": state.get("test_case"),
        }
        task_store.save(task_id, task)

    if not reserve_task(task_id):
        raise HTTPException(
            status_code=409,
            detail="Task is already running",
        )

    background_tasks.add_task(
        run_bugfix_task,
        task_store,
        task_id,
        state,
        task_reserved=True,
    )

    return {
        "status": "resuming",
        "resumable": True,
        "task_id": task_id,
        "session_id": request.session_id,
        "checkpoint_id": snapshot.get("checkpoint_id"),
        "current_step": state.get("current_step", 0),
        "total_steps": len(state.get("plan", [])),
    }

@app.get("/api/session/list", response_model=SessionListResponse)
async def list_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    username: str = Depends(get_current_user),
):
    task_page = task_store.list_tasks(
        username=username,
        limit=limit,
    )

    sessions = []

    for task in task_page["tasks"]:
        session_id = task.get("session_id")
        if not session_id:
            continue

        snapshot = await task_persistence.load_agent_state(session_id)
        state = snapshot.get("state", {}) if snapshot else {}

        state_username = state.get("username")
        owner_matches = state_username in (None, username)

        resumable = (
            snapshot is not None
            and bool(state.get("last_node"))
            and state.get("done") is not True
            and owner_matches
        )

        sessions.append(
            {
                "session_id": session_id,
                "task_id": task["task_id"],
                "status": task.get("status", "unknown"),
                "progress": task.get("progress", 0.0),
                "current_step": task.get("current_step"),
                "total_steps": task.get("total_steps"),
                "created_at": task.get("created_at"),
                "resumable": resumable,
            }
        )

    return {
        "sessions": sessions,
        "total": task_page["total"],
    }

@app.get("/api/stats", response_model=TaskStatsResponse)
def get_task_stats(
    username: str = Depends(get_current_user),
):
    return {
        "tasks": task_store.get_task_stats(username),
    }