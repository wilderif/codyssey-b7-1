"""Auth FastAPI dependency의 인증·권한 계약을 검증한다."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user_id, require_admin
from app.auth.models import ADMIN_ROLE
from app.auth.repository import create_user


def make_request(session: Mapping[str, object]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "session": dict(session),
        }
    )


def test_get_current_user_id_returns_session_user_id() -> None:
    request = make_request({"user_id": 42})

    assert get_current_user_id(request) == 42


@pytest.mark.parametrize(
    "session",
    [
        {},
        {"user_id": None},
        {"user_id": "42"},
        {"user_id": True},
        {"user_id": 0},
        {"user_id": -1},
    ],
)
def test_get_current_user_id_rejects_invalid_session(
    session: Mapping[str, object],
) -> None:
    with pytest.raises(HTTPException) as error:
        get_current_user_id(make_request(session))

    assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert error.value.detail == "로그인이 필요합니다."


def test_require_admin_returns_admin_user_id(db: Session) -> None:
    admin = create_user(
        db=db,
        username="admin",
        password_hash="test-hash",
        role=ADMIN_ROLE,
    )

    assert require_admin(make_request({"user_id": admin.id}), db) == admin.id


def test_require_admin_rejects_non_admin(db: Session) -> None:
    user = create_user(
        db=db,
        username="regular-user",
        password_hash="test-hash",
    )

    with pytest.raises(HTTPException) as error:
        require_admin(make_request({"user_id": user.id}), db)

    assert error.value.status_code == status.HTTP_403_FORBIDDEN
    assert error.value.detail == "접근 권한이 없습니다."


@pytest.mark.parametrize("user_id", [None, 999])
def test_require_admin_redirects_unauthenticated_user(
    db: Session,
    user_id: int | None,
) -> None:
    session = {} if user_id is None else {"user_id": user_id}

    with pytest.raises(HTTPException) as error:
        require_admin(make_request(session), db)

    assert error.value.status_code == status.HTTP_303_SEE_OTHER
    assert error.value.headers == {"Location": "/login"}
