import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class TaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._redis = None

        try:
            import redis

            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", "6379"))

            client = redis.Redis(
                host=host,
                port=port,
                db=0,
                decode_responses=True,
                socket_connect_timeout=3,
            )
            client.ping()

            self._redis = client
            logger.info("Connected to Redis at %s:%s", host, port)
        except Exception as exc:
            logger.warning(
                "Redis unavailable; using in-memory task store: %s",
                exc,
            )

    @staticmethod
    def _key(task_id: str) -> str:
        return f"bugfix:task:{task_id}"

    def save(self, task_id: str, task: dict[str, Any]) -> None:
        if self._redis is not None:
            self._redis.set(
                self._key(task_id),
                json.dumps(task, ensure_ascii=False),
            )
        else:
            self._tasks[task_id] = task

    def update(
        self,
        task_id: str,
        changes: dict[str, Any],
    ) -> dict[str, Any] | None:
        task = self.get(task_id)
        if task is None:
            return None

        task.update(changes)
        self.save(task_id, task)
        return task

    def get(self, task_id: str) -> dict[str, Any] | None:
        if self._redis is not None:
            payload = self._redis.get(self._key(task_id))
            if payload is None:
                return None
            return json.loads(payload)

        return self._tasks.get(task_id)

    def list_tasks(
        self,
        username:str | None = None,
        status: str | None = None,
        limit: int = 20,

    ) -> dict[str, Any]:
        tasks = []

        if self._redis is not None:
            pattern = self._key("*")

            for key in self._redis.scan_iter(match=pattern):
                payload = self._redis.get(key)

                if payload is None:
                    continue

                task = json.loads(payload)
                task.setdefault("task_id", key.rsplit(":", 1)[-1])
                tasks.append(task)
        else:
            tasks = [
                dict(task)
                for task in self._tasks.values()
            ]

        if status:
            tasks = [
                task
                for task in tasks
                if task.get("status") == status
            ]
        #按用户名筛选
        if username:
            tasks = [
                task
                for task in tasks
                if task.get("username") == username
            ]
        tasks.sort(
            key=lambda task: task.get("created_at", ""),
            reverse=True,
        )

        total = len(tasks)

        return {
            "tasks": tasks[:limit],
            "total": total,
        }

    def get_task_stats(self, username: str) -> dict[str, int]:
        stats = {
            "total": 0,
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "no_bugs_found": 0,
        }

        if self._redis is not None:
            tasks = []

            for key in self._redis.scan_iter(match=self._key("*")):
                payload = self._redis.get(key)
                if payload is not None:
                    tasks.append(json.loads(payload))
        else:
            tasks = list(self._tasks.values())

        for task in tasks:
            if task.get("username") != username:
                continue

            stats["total"] += 1
            status = task.get("status")

            if status in {
                "pending",
                "running",
                "completed",
                "failed",
                "no_bugs_found",
            }:
                stats[status] += 1

        return stats