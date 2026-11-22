from typing import Any


class TaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}

    def save(self, task_id: str, task: dict[str, Any]) -> None:
        self._tasks[task_id] = task

    def update(self,task_id: str,changes: dict[str, Any],) -> dict[str, Any] | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None

        task.update(changes)
        return task

    def get(self, task_id: str) -> dict[str, Any] | None:
        return self._tasks.get(task_id)