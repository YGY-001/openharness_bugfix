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