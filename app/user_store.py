import json
import logging
import os
from typing import Any


logger = logging.getLogger(__name__)


class UserStore:
    def __init__(self) -> None:
        self._users: dict[str, dict[str, Any]] = {}
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
            logger.info("Connected to Redis for user storage at %s:%s", host, port)
        except Exception as exc:
            logger.warning(
                "Redis unavailable; using in-memory user store: %s",
                exc,
            )

    @staticmethod
    def _key(username: str) -> str:
        return f"bugfix:user:{username}"

    def create_user(
        self,
        username: str,
        password_hash: str,
        email: str | None = None,
    ) -> bool:
        user = {
            "username": username,
            "password_hash": password_hash,
            "email": email,
        }

        if self._redis is not None:
            created = self._redis.set(
                self._key(username),
                json.dumps(user, ensure_ascii=False),
                nx=True,
            )
            return bool(created)

        if username in self._users:
            return False

        self._users[username] = user
        return True

    def get_user(self, username: str) -> dict[str, Any] | None:
        if self._redis is not None:
            payload = self._redis.get(self._key(username))
            if payload is None:
                return None
            return json.loads(payload)

        user = self._users.get(username)
        return dict(user) if user is not None else None