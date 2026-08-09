"""Password를 안전하게 처리하는 공통 보안 helper다."""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ALGORITHM = (
    "pbkdf2_sha256"  # Password-Based Key Derivation Function, sha256 알고리즘 사용
)
_ITERATIONS = 600_000  # SHA256은 결과가 너무 빨리 나오므로 반복실행하여 brute-force 공격을 어렵게 한다.
_SALT_BYTES = (
    16  # 값을 더해서 같은 비밀번호도 다르게 저장. 레인보우 테이블 공격을 어렵게 한다.
)
_DERIVED_KEY_BYTES = 32  # SHA256은 32바이트(256비트) 길이의 해시를 생성한다.


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


def verify_password(password: str, encoded_hash: str) -> bool:
    """Password가 저장된 hash와 일치하는지 안전하게 확인한다."""

    try:  # DB -> pbkdf2_sha256$600000$<salt>$<derived_key>
        algorithm, iterations_text, salt_hex, derived_key_hex = encoded_hash.split("$")
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(derived_key_hex)
    except (TypeError, ValueError):
        return False

    if (  # hasing 형식 비교
        algorithm != _ALGORITHM
        or iterations != _ITERATIONS
        or len(salt) != _SALT_BYTES
        or len(expected_key) != _DERIVED_KEY_BYTES
    ):
        return False

    candidate_key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=_DERIVED_KEY_BYTES,
    )
    return hmac.compare_digest(
        candidate_key, expected_key
    )  # 불일치 타이밍을 계산해서 공격자가 추측하지 못하도록 안전하게 비교한다.
