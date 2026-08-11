"""사용자 인증 Service의 credential 검증 계약을 확인한다."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.repository import create_user
from app.auth.service import authenticate_user
from app.core.security import hash_password

_PASSWORD = "  correct-password  "


@pytest.fixture(scope="module")
def encoded_password() -> str:
    """인증 test에서 공유하는 password hash를 반환한다."""

    return hash_password(_PASSWORD)


def _save_user(*, db: Session, password_hash: str) -> User:
    user = create_user(
        db=db,
        username="test-user",
        password_hash=password_hash,
    )
    db.commit()
    return user


def test_authenticate_user_returns_user_for_valid_credentials(
    db: Session,
    encoded_password: str,
) -> None:
    user = _save_user(db=db, password_hash=encoded_password)

    authenticated_user = authenticate_user(
        db=db,
        username="  test-user  ",
        password=_PASSWORD,
    )

    assert authenticated_user is not None
    assert authenticated_user.id == user.id


def test_authenticate_user_does_not_trim_password(
    db: Session,
    encoded_password: str,
) -> None:
    _save_user(db=db, password_hash=encoded_password)

    authenticated_user = authenticate_user(
        db=db,
        username="test-user",
        password=_PASSWORD.strip(),
    )

    assert authenticated_user is None


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("test-user", "wrong-password"),
        ("missing-user", _PASSWORD),
    ],
)
def test_authenticate_user_returns_none_for_invalid_credentials(
    db: Session,
    encoded_password: str,
    username: str,
    password: str,
) -> None:
    _save_user(db=db, password_hash=encoded_password)

    assert (
        authenticate_user(
            db=db,
            username=username,
            password=password,
        )
        is None
    )


def test_authenticate_user_rejects_malformed_stored_hash(db: Session) -> None:
    _save_user(db=db, password_hash="malformed-hash")

    authenticated_user = authenticate_user(
        db=db,
        username="test-user",
        password=_PASSWORD,
    )

    assert authenticated_user is None
