"""Password hashing helper의 보안 계약을 검증한다."""

from __future__ import annotations

import hashlib
import hmac

from app.core.security import hash_password


def test_hash_password_creates_verifiable_non_plaintext_hash() -> None:
    password = "correct-horse-battery-staple"

    hashed = hash_password(password)

    assert hashed != password
    assert _verify_password(password=password, encoded_hash=hashed)


def test_hash_password_uses_a_unique_salt() -> None:
    password = "same-password"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash
    assert _verify_password(password=password, encoded_hash=first_hash)
    assert _verify_password(password=password, encoded_hash=second_hash)


def test_hash_password_stores_algorithm_parameters_and_random_salt() -> None:
    algorithm, iterations, salt, derived_key = hash_password("password").split("$")

    assert algorithm == "pbkdf2_sha256"
    assert iterations == "600000"
    assert len(bytes.fromhex(salt)) == 16
    assert len(bytes.fromhex(derived_key)) == 32


def _verify_password(*, password: str, encoded_hash: str) -> bool:
    algorithm, iterations, salt_hex, derived_key_hex = encoded_hash.split("$")
    assert algorithm == "pbkdf2_sha256"

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        int(iterations),
        dklen=32,
    )
    return hmac.compare_digest(candidate, bytes.fromhex(derived_key_hex))
