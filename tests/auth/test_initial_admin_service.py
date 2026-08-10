"""Initial admin account의 startup bootstrap 계약을 검증한다."""

from __future__ import annotations

import logging

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.auth.service as service_module
from app.auth.models import ADMIN_ROLE, USER_ROLE, User
from app.auth.repository import create_user, get_user_by_username
from app.auth.service import (
    AdminBootstrapError,
    AdminBootstrapReason,
    ensure_initial_admin,
)
from app.core.config import Settings
from app.core.security import verify_password


def test_ensure_initial_admin_creates_hashed_admin_account(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
) -> None:
    password = "initial-admin-password"
    _configure_admin(monkeypatch, password=password)

    ensure_initial_admin(db=db)

    assert not db.in_transaction()
    admin = get_user_by_username(db=db, username="admin")
    assert admin is not None
    assert admin.role == ADMIN_ROLE
    assert admin.password_hash != password
    assert verify_password(password, admin.password_hash)


def test_ensure_initial_admin_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
) -> None:
    _configure_admin(monkeypatch, password="initial-admin-password")
    monkeypatch.setattr(service_module, "hash_password", lambda _password: "test-hash")

    ensure_initial_admin(db=db)
    ensure_initial_admin(db=db)

    assert not db.in_transaction()
    assert db.scalar(select(func.count(User.id))) == 1


def test_ensure_initial_admin_preserves_existing_admin_without_password(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
) -> None:
    admin = create_user(
        db=db,
        username="existing-admin",
        password_hash="existing-hash",
        role=ADMIN_ROLE,
    )
    admin_id = admin.id
    db.commit()
    _configure_admin(monkeypatch)

    def fail_if_called(_password: str) -> str:
        raise AssertionError("hash_password must not run for an existing admin")

    monkeypatch.setattr(service_module, "hash_password", fail_if_called)

    ensure_initial_admin(db=db)

    assert not db.in_transaction()
    saved = db.get(User, admin_id)
    assert saved is not None
    assert saved.password_hash == "existing-hash"
    assert saved.role == ADMIN_ROLE
    assert get_user_by_username(db=db, username="admin") is None


def test_ensure_initial_admin_rejects_missing_password(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _configure_admin(monkeypatch)

    with (
        caplog.at_level(logging.ERROR, logger=service_module.__name__),
        pytest.raises(AdminBootstrapError) as captured,
    ):
        ensure_initial_admin(db=db)

    assert captured.value.reason == AdminBootstrapReason.MISSING_INITIAL_PASSWORD
    assert not db.in_transaction()
    _assert_safe_failure_log(
        caplog,
        reason=AdminBootstrapReason.MISSING_INITIAL_PASSWORD,
    )


@pytest.mark.parametrize("password", ["", "short", "x" * 73])
def test_ensure_initial_admin_rejects_invalid_password_length(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    caplog: pytest.LogCaptureFixture,
    password: str,
) -> None:
    _configure_admin(monkeypatch, password=password)

    with (
        caplog.at_level(logging.ERROR, logger=service_module.__name__),
        pytest.raises(AdminBootstrapError) as captured,
    ):
        ensure_initial_admin(db=db)

    assert captured.value.reason == AdminBootstrapReason.INVALID_INITIAL_PASSWORD
    if password:
        assert password not in str(captured.value)
        assert password not in caplog.text
    assert not db.in_transaction()
    _assert_safe_failure_log(
        caplog,
        reason=AdminBootstrapReason.INVALID_INITIAL_PASSWORD,
    )


def test_ensure_initial_admin_rejects_existing_non_admin_account(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    user = create_user(
        db=db,
        username="admin",
        password_hash="existing-hash",
        role=USER_ROLE,
    )
    user_id = user.id
    db.commit()
    _configure_admin(monkeypatch, password="initial-admin-password")

    with (
        caplog.at_level(logging.ERROR, logger=service_module.__name__),
        pytest.raises(AdminBootstrapError) as captured,
    ):
        ensure_initial_admin(db=db)

    assert captured.value.reason == AdminBootstrapReason.INVALID_ADMIN_ROLE
    assert not db.in_transaction()
    saved = db.get(User, user_id)
    assert saved is not None
    assert saved.role == USER_ROLE
    assert saved.password_hash == "existing-hash"
    _assert_safe_failure_log(
        caplog,
        reason=AdminBootstrapReason.INVALID_ADMIN_ROLE,
    )


def test_ensure_initial_admin_contains_lookup_error(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sensitive_error = "SELECT password_hash Cookie secret traceback"
    _configure_admin(monkeypatch, password="initial-admin-password")

    def fail_lookup(**_kwargs: object) -> User | None:
        raise RuntimeError(sensitive_error)

    monkeypatch.setattr(service_module, "get_admin_user", fail_lookup)

    with (
        caplog.at_level(logging.ERROR, logger=service_module.__name__),
        pytest.raises(AdminBootstrapError) as captured,
    ):
        ensure_initial_admin(db=db)

    assert captured.value.reason == AdminBootstrapReason.DB_ERROR
    assert captured.value.__cause__ is None
    assert sensitive_error not in str(captured.value)
    assert sensitive_error not in caplog.text
    assert not db.in_transaction()
    _assert_safe_failure_log(caplog, reason=AdminBootstrapReason.DB_ERROR)


def test_ensure_initial_admin_rolls_back_create_error(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sensitive_error = "INSERT password_hash database secret"
    _configure_admin(monkeypatch, password="initial-admin-password")
    monkeypatch.setattr(service_module, "hash_password", lambda _password: "hash")

    def fail_create(**_kwargs: object) -> User:
        raise RuntimeError(sensitive_error)

    monkeypatch.setattr(service_module, "create_user", fail_create)

    with (
        caplog.at_level(logging.ERROR, logger=service_module.__name__),
        pytest.raises(AdminBootstrapError) as captured,
    ):
        ensure_initial_admin(db=db)

    assert captured.value.reason == AdminBootstrapReason.DB_ERROR
    assert sensitive_error not in str(captured.value)
    assert sensitive_error not in caplog.text
    assert not db.in_transaction()
    assert db.scalar(select(func.count(User.id))) == 0
    _assert_safe_failure_log(caplog, reason=AdminBootstrapReason.DB_ERROR)


def test_ensure_initial_admin_rolls_back_commit_error(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sensitive_error = "commit failed with password_hash secret"
    _configure_admin(monkeypatch, password="initial-admin-password")
    monkeypatch.setattr(service_module, "hash_password", lambda _password: "hash")

    def fail_commit() -> None:
        raise RuntimeError(sensitive_error)

    monkeypatch.setattr(db, "commit", fail_commit)

    with (
        caplog.at_level(logging.ERROR, logger=service_module.__name__),
        pytest.raises(AdminBootstrapError) as captured,
    ):
        ensure_initial_admin(db=db)

    assert captured.value.reason == AdminBootstrapReason.DB_ERROR
    assert sensitive_error not in str(captured.value)
    assert sensitive_error not in caplog.text
    assert not db.in_transaction()
    assert db.scalar(select(func.count(User.id))) == 0
    _assert_safe_failure_log(caplog, reason=AdminBootstrapReason.DB_ERROR)


def _configure_admin(
    monkeypatch: pytest.MonkeyPatch,
    *,
    password: str | None = None,
) -> None:
    values: dict[str, object] = {"ADMIN_USERNAME": "admin"}
    if password is not None:
        values["ADMIN_INITIAL_PASSWORD"] = password
    monkeypatch.setattr(service_module, "settings", Settings.model_validate(values))


def _assert_safe_failure_log(
    caplog: pytest.LogCaptureFixture,
    *,
    reason: AdminBootstrapReason,
) -> None:
    records = [
        record for record in caplog.records if record.name == service_module.__name__
    ]
    assert [record.getMessage() for record in records] == [
        f"admin_bootstrap_failed reason={reason.value}"
    ]
    assert all(record.exc_info is None for record in records)
    assert "Traceback" not in caplog.text
