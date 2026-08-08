"""Password를 안전하게 처리하는 공통 보안 helper다."""

from __future__ import annotations

import hashlib
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 600_000
_SALT_BYTES = 16
_DERIVED_KEY_BYTES = 32


def hash_password(password: str) -> str:
    """Password 원문을 단방향 hash로 변환한다."""

    salt = secrets.token_bytes(_SALT_BYTES)
    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _ITERATIONS,
        dklen=_DERIVED_KEY_BYTES,
    )
    return f"{_ALGORITHM}${_ITERATIONS}${salt.hex()}${derived_key.hex()}"
