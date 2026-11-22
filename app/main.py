from datetime import datetime
from uuid import uuid4
from fastapi import FastAPI, HTTPException, BackgroundTasks
from app.schemas import BugSubmitRequest, BugSubmitAccepted, BugTaskResponse

from app.task_store import TaskStore
from app.task_runner import run_bugfix_task

app = FastAPI(title="Bugfix Agent")
task_store = TaskStore()

@app.get("/api/health")
async def health():
    return {"status": "ok"}



@app.post("/api/bug/submit", response_model=BugSubmitAccepted)
async def submit_bug(bug: BugSubmitRequest,background_tasks:BackgroundTasks):
    now = datetime.now()
    task_id = f"task_{now:%Y%m%d%H%M%S}_{uuid4().hex[:6]}"
    session_id = f"session-{task_id}"

    task = {
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
async def get_bug_task(task_id: str):
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task