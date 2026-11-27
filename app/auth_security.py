import base64
import hashlib
import hmac
import secrets
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _jwt_config() -> tuple[str, str, int]:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET is missing from environment")

    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    expiration_minutes = int(
        os.getenv("JWT_EXPIRATION_MINUTES", "60")
    )

    if expiration_minutes <= 0:
        raise RuntimeError("JWT_EXPIRATION_MINUTES must be positive")

    return secret, algorithm, expiration_minutes


def create_access_token(username: str) -> str:
    secret, algorithm, expiration_minutes = _jwt_config()

    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + timedelta(minutes=expiration_minutes),
    }

    return jwt.encode(
        payload,
        secret,
        algorithm=algorithm,
    )


def decode_access_token(token: str) -> dict:
    secret, algorithm, _ = _jwt_config()

    return jwt.decode(
        token,
        secret,
        algorithms=[algorithm],
    )

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 310_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _ITERATIONS,
    )

    salt_text = base64.b64encode(salt).decode("ascii")
    digest_text = base64.b64encode(digest).decode("ascii")

    return f"{_ALGORITHM}${_ITERATIONS}${salt_text}${digest_text}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = stored_hash.split("$", 3)

        if algorithm != _ALGORITHM:
            return False

        iterations = int(iterations_text)
        salt = base64.b64decode(salt_text, validate=True)
        expected_digest = base64.b64decode(digest_text, validate=True)

        actual_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )

        return hmac.compare_digest(actual_digest, expected_digest)
    except (ValueError, TypeError):
        return False