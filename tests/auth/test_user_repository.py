"""Auth User repository의 기본 조회·생성 계약을 검증한다."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.auth.models import ADMIN_ROLE, USER_ROLE
from app.auth.repository import (
    create_user,
    get_admin_user,
    get_user_by_id,
    get_user_by_username,
)


def test_create_user_flushes_without_committing(db: Session) -> None:
    user = create_user(
        db=db,
        username="new-user",
        password_hash="test-hash",
    )

    assert user.id > 0
    assert user.role == USER_ROLE
    assert db.in_transaction()

    db.rollback()

    assert get_user_by_id(db=db, user_id=user.id) is None


def test_create_and_get_admin_user(db: Session) -> None:
    user = create_user(
        db=db,
        username="admin-user",
        password_hash="admin-hash",
        role=ADMIN_ROLE,
    )

    assert get_user_by_id(db=db, user_id=user.id) is user
    assert get_user_by_username(db=db, username=user.username) is user


def test_get_user_returns_none_when_not_found(db: Session) -> None:
    assert get_user_by_id(db=db, user_id=999) is None
    assert get_user_by_username(db=db, username="missing-user") is None


def test_get_admin_user_returns_admin_regardless_of_username(db: Session) -> None:
    create_user(
        db=db,
        username="regular-user",
        password_hash="user-hash",
    )
    admin = create_user(
        db=db,
        username="configured-elsewhere",
        password_hash="admin-hash",
        role=ADMIN_ROLE,
    )

    assert get_admin_user(db=db) is admin


def test_get_admin_user_returns_none_without_admin_role(db: Session) -> None:
    create_user(
        db=db,
        username="admin",
        password_hash="user-hash",
    )

    assert get_admin_user(db=db) is None
