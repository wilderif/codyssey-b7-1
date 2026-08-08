"""Auth User model의 DB schema 계약을 검증한다."""

from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.auth.models import ADMIN_ROLE, USER_ROLE, User


def test_user_role_defaults_to_user(db: Session) -> None:
    user = User(username="default-role", password_hash="test-hash")
    db.add(user)
    db.flush()

    assert user.role == USER_ROLE


def test_user_accepts_admin_role(db: Session) -> None:
    user = User(
        username="admin-role",
        password_hash="test-hash",
        role=ADMIN_ROLE,
    )
    db.add(user)
    db.flush()

    assert user.role == ADMIN_ROLE


def test_user_role_column_is_not_nullable(db: Session) -> None:
    role_column = next(
        column
        for column in inspect(db.get_bind()).get_columns("users")
        if column["name"] == "role"
    )

    assert role_column["nullable"] is False
