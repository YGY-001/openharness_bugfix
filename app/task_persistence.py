import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class TaskPersistence:
    def __init__(
        self,
        storage_dir: str = "data/task_persistence",
        default_ttl: int = 7 * 24 * 60 * 60,
    ) -> None:
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)

        self._default_ttl = default_ttl
        self._redis = None
        self._redis_checked = False

    @staticmethod
    def _state_key(session_id: str) -> str:
        return f"bugfix:state:{session_id}"

    def _state_file(self, session_id: str) -> Path:
        safe_id = "".join(
            char for char in session_id
            if char.isalnum() or char in "-_."
        )
        return self._storage_dir / f"{safe_id}.json"

    async def _get_redis(self):
        if self._redis_checked:
            return self._redis

        self._redis_checked = True

        try:
            import redis.asyncio as redis_async

            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", "6379"))

            client = redis_async.Redis(
                host=host,
                port=port,
                db=0,
                decode_responses=True,
                socket_connect_timeout=3,
            )
            await client.ping()

            self._redis = client
            logger.info("TaskPersistence connected to Redis at %s:%s", host, port)
        except Exception as exc:
            logger.warning(
                "TaskPersistence is using file storage: %s",
                exc,
            )

        return self._redis

    async def save_agent_state(
        self,
        session_id: str,
        state: dict[str, Any],
        checkpoint_id: str | None = None,
    ) -> str:
        snapshot = {
            "session_id": session_id,
            "checkpoint_id": checkpoint_id or uuid4().hex[:8],
            "saved_at": datetime.now().isoformat(),
            "state": state,
        }
        payload = json.dumps(snapshot, ensure_ascii=False)

        redis_client = await self._get_redis()
        if redis_client is not None:
            try:
                await redis_client.set(
                    self._state_key(session_id),
                    payload,
                    ex=self._default_ttl,
                )
                return self._state_key(session_id)
            except Exception as exc:
                logger.warning(
                    "Redis state save failed; using file storage: %s",
                    exc,
                )
                self._redis = None

        path = self._state_file(session_id)
        path.write_text(payload, encoding="utf-8")
        return str(path)

    async def load_agent_state(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:
        redis_client = await self._get_redis()

        if redis_client is not None:
            try:
                payload = await redis_client.get(self._state_key(session_id))
                if payload is not None:
                    return json.loads(payload)
            except Exception as exc:
                logger.warning(
                    "Redis state load failed; checking file storage: %s",
                    exc,
                )
                self._redis = None

        path = self._state_file(session_id)
        if not path.exists():
            return None

        return json.loads(path.read_text(encoding="utf-8"))