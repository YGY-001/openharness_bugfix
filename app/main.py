from datetime import datetime
from uuid import uuid4
from fastapi import FastAPI, HTTPException
from app.schemas import BugSubmitRequest, BugSubmitAccepted, BugTaskResponse

from app.task_store import TaskStore

app = FastAPI(title="Bugfix Agent")
task_store = TaskStore()

@app.get("/api/health")
async def health():
    return {"status": "ok"}



@app.post("/api/bug/submit", response_model=BugSubmitAccepted)
async def submit_bug(bug: BugSubmitRequest):
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
    }
    task_store.save(task_id, task)
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