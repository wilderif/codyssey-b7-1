"""회원가입 입력 validation과 User transaction 계약을 검증한다."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

import app.auth.service as service_module
from app.auth.models import USER_ROLE, User
from app.auth.service import RegistrationError, RegistrationReason, register_user
from app.core.security import verify_password


def test_register_user_trims_username_hashes_password_and_commits(
    db: Session,
) -> None:
    password = "  strong-password  "

    user = register_user(
        db=db,
        username="  new-user  ",
        password=password,
    )

    identity = inspect(user).identity
    assert identity is not None
    user_id = identity[0]
    assert not db.in_transaction()

    saved = db.get(User, user_id)
    assert saved is not None
    assert saved.username == "new-user"
    assert saved.role == USER_ROLE
    assert saved.password_hash != password
    assert verify_password(password, saved.password_hash)
    assert not verify_password(password.strip(), saved.password_hash)


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("abc", "password"),
        ("u" * 30, "비" * 72),
    ],
)
def test_register_user_accepts_length_boundaries(
    db: Session,
    username: str,
    password: str,
) -> None:
    user = register_user(db=db, username=username, password=password)

    assert inspect(user).identity is not None
    assert not db.in_transaction()


@pytest.mark.parametrize(
    ("username", "password", "expected_reason"),
    [
        ("ab", "password", RegistrationReason.USERNAME_LENGTH),
        ("u" * 31, "password", RegistrationReason.USERNAME_LENGTH),
        ("valid-user", "p" * 7, RegistrationReason.PASSWORD_LENGTH),
        ("valid-user", "비" * 73, RegistrationReason.PASSWORD_LENGTH),
    ],
)
def test_register_user_rejects_invalid_lengths_before_hashing(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    username: str,
    password: str,
    expected_reason: RegistrationReason,
) -> None:
    def fail_if_called(_password: str) -> str:
        raise AssertionError("hash_password must not run for invalid input")

    monkeypatch.setattr(service_module, "hash_password", fail_if_called)

    with pytest.raises(RegistrationError) as captured:
        register_user(db=db, username=username, password=password)

    assert captured.value.reason == expected_reason
    assert password not in str(captured.value)
    assert db.scalar(select(func.count(User.id))) == 0


def test_register_user_rejects_duplicate_normalized_username(db: Session) -> None:
    db.add(User(username="taken-user", password_hash="existing-hash"))
    db.commit()

    with pytest.raises(RegistrationError) as captured:
        register_user(
            db=db,
            username="  taken-user  ",
            password="new-password",
        )

    assert captured.value.reason == RegistrationReason.DUPLICATE_USERNAME
    assert "new-password" not in str(captured.value)
    assert not db.in_transaction()
    assert db.scalar(select(func.count(User.id))) == 1


def test_register_user_maps_unique_constraint_race_to_duplicate_error(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
) -> None:
    db.add(User(username="race-user", password_hash="existing-hash"))
    db.commit()
    monkeypatch.setattr(
        service_module,
        "get_user_by_username",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        service_module,
        "hash_password",
        lambda _password: "new-hash",
    )

    with pytest.raises(RegistrationError) as captured:
        register_user(
            db=db,
            username="race-user",
            password="race-password",
        )

    assert captured.value.reason == RegistrationReason.DUPLICATE_USERNAME
    assert "race-password" not in str(captured.value)
    assert not db.in_transaction()
    assert db.scalar(select(func.count(User.id))) == 1


def test_register_user_rolls_back_unexpected_persistence_error(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
) -> None:
    password = "secret-password"

    def fail_create_user(**_kwargs: object) -> User:
        raise RuntimeError("database save failed")

    monkeypatch.setattr(service_module, "hash_password", lambda _password: "hash")
    monkeypatch.setattr(service_module, "create_user", fail_create_user)

    with pytest.raises(RuntimeError, match="database save failed") as captured:
        register_user(db=db, username="new-user", password=password)

    assert password not in str(captured.value)
    assert not db.in_transaction()


def test_register_user_rolls_back_commit_failure(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
) -> None:
    def fail_commit() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(service_module, "hash_password", lambda _password: "hash")
    monkeypatch.setattr(db, "commit", fail_commit)

    with pytest.raises(RuntimeError, match="commit failed"):
        register_user(
            db=db,
            username="new-user",
            password="secret-password",
        )

    assert not db.in_transaction()
    assert db.scalar(select(func.count(User.id))) == 0
