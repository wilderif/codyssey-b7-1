"""User persistence를 위한 기본 조회·생성 함수를 제공한다."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import ADMIN_ROLE, USER_ROLE, User


def get_user_by_id(*, db: Session, user_id: int) -> User | None:
    """ID가 일치하는 User를 반환한다."""

    return db.scalar(select(User).where(User.id == user_id))


def get_user_by_username(*, db: Session, username: str) -> User | None:
    """username이 일치하는 User를 반환한다."""

    return db.scalar(select(User).where(User.username == username))


def get_admin_user(*, db: Session) -> User | None:
    """관리자 역할을 가진 User 한 명을 반환한다."""

    return db.scalar(
        select(User).where(User.role == ADMIN_ROLE).order_by(User.id).limit(1)
    )


def create_user(
    *,
    db: Session,
    username: str,
    password_hash: str,
    role: str = USER_ROLE,
) -> User:
    """User를 추가하고 생성된 field를 사용할 수 있도록 flush한다."""

    user = User(
        username=username,
        password_hash=password_hash,
        role=role,
    )
    db.add(user)
    db.flush()
    return user
