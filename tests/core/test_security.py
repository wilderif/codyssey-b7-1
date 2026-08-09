"""Password hashing helper의 보안 계약을 검증한다."""

from __future__ import annotations

import pytest

from app.core.security import hash_password, verify_password

_VALID_SALT_HEX = "00" * 16
_VALID_DERIVED_KEY_HEX = "00" * 32


def test_hash_password_creates_verifiable_non_plaintext_hash() -> None:
    password = "correct-horse-battery-staple"

    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed)


def test_hash_password_uses_a_unique_salt() -> None:
    password = "same-password"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash
    assert verify_password(password, first_hash)
    assert verify_password(password, second_hash)


def test_hash_password_stores_algorithm_parameters_and_random_salt() -> None:
    algorithm, iterations, salt, derived_key = hash_password("password").split("$")

    assert algorithm == "pbkdf2_sha256"
    assert iterations == "600000"
    assert len(bytes.fromhex(salt)) == 16
    assert len(bytes.fromhex(derived_key)) == 32


def test_verify_password_rejects_wrong_password() -> None:
    encoded_hash = hash_password("correct-password")

    assert not verify_password("wrong-password", encoded_hash)


@pytest.mark.parametrize(
    "encoded_hash",
    [
        "not-a-password-hash",
        f"unsupported$600000${_VALID_SALT_HEX}${_VALID_DERIVED_KEY_HEX}",
        f"pbkdf2_sha256$invalid${_VALID_SALT_HEX}${_VALID_DERIVED_KEY_HEX}",
        f"pbkdf2_sha256$1${_VALID_SALT_HEX}${_VALID_DERIVED_KEY_HEX}",
        f"pbkdf2_sha256$600000$invalid${_VALID_DERIVED_KEY_HEX}",
        f"pbkdf2_sha256$600000${_VALID_SALT_HEX}$00",
    ],
)
def test_verify_password_rejects_malformed_or_unsupported_hash(
    encoded_hash: str,
) -> None:
    assert not verify_password("password", encoded_hash)
