"""Auth FastAPI dependency의 인증·권한 계약을 검증한다."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AuthenticatedUser,
    clear_session_user_id,
    get_current_user_id,
    get_optional_authenticated_user,
    get_session_user_id,
    require_admin,
    require_authenticated_user,
    set_session_user_id,
)
from app.auth.models import ADMIN_ROLE, USER_ROLE
from app.auth.repository import create_user


def _make_request(session: Mapping[str, object]) -> Request:
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


def test_set_session_user_id_replaces_existing_session_data() -> None:
    request = _make_request({"stale": "value", "user_id": 1})

    set_session_user_id(request, user_id=42)

    assert request.session == {"user_id": 42}
    assert get_session_user_id(request) == 42


@pytest.mark.parametrize("user_id", [True, 0, -1])
def test_set_session_user_id_rejects_invalid_id_without_changing_session(
    user_id: int,
) -> None:
    request = _make_request({"stale": "value"})

    with pytest.raises(ValueError, match="user_id"):
        set_session_user_id(request, user_id=user_id)

    assert request.session == {"stale": "value"}


def test_clear_session_user_id_removes_all_session_data() -> None:
    request = _make_request({"user_id": 42, "stale": "value"})

    clear_session_user_id(request)

    assert request.session == {}
    assert get_session_user_id(request) is None


def test_get_current_user_id_returns_existing_session_user_id(db: Session) -> None:
    user = create_user(
        db=db,
        username="json-auth-user",
        password_hash="test-hash",
    )
    request = _make_request({"user_id": user.id})

    assert get_current_user_id(request, db) == user.id


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
    db: Session,
) -> None:
    with pytest.raises(HTTPException) as error:
        get_current_user_id(_make_request(session), db)

    assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert error.value.detail == "로그인이 필요합니다."


def test_get_current_user_id_clears_deleted_user_session(db: Session) -> None:
    user = create_user(
        db=db,
        username="deleted-json-auth-user",
        password_hash="test-hash",
    )
    db.commit()
    request = _make_request({"user_id": user.id, "stale": "value"})
    db.delete(user)
    db.commit()

    with pytest.raises(HTTPException) as error:
        get_current_user_id(request, db)

    assert request.session == {}
    assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert error.value.detail == "로그인이 필요합니다."


@pytest.mark.parametrize(
    ("role", "expected_is_admin"),
    [(USER_ROLE, False), (ADMIN_ROLE, True)],
)
def test_require_authenticated_user_returns_minimal_user_data(
    db: Session,
    role: str,
    expected_is_admin: bool,
) -> None:
    user = create_user(
        db=db,
        username=f"{role}-user",
        password_hash="test-hash",
        role=role,
    )

    result = require_authenticated_user(_make_request({"user_id": user.id}), db)

    assert result == AuthenticatedUser(
        user_id=user.id,
        is_admin=expected_is_admin,
    )


@pytest.mark.parametrize(
    ("role", "expected_is_admin"),
    [(USER_ROLE, False), (ADMIN_ROLE, True)],
)
def test_get_optional_authenticated_user_returns_minimal_user_data(
    db: Session,
    role: str,
    expected_is_admin: bool,
) -> None:
    user = create_user(
        db=db,
        username=f"optional-{role}-user",
        password_hash="test-hash",
        role=role,
    )

    result = get_optional_authenticated_user(
        _make_request({"user_id": user.id}),
        db,
    )

    assert result == AuthenticatedUser(
        user_id=user.id,
        is_admin=expected_is_admin,
    )


@pytest.mark.parametrize("user_id", [None, "1", True, 0, -1, 999])
def test_get_optional_authenticated_user_clears_stale_session(
    db: Session,
    user_id: object,
) -> None:
    request = _make_request({"user_id": user_id, "stale": "value"})

    assert get_optional_authenticated_user(request, db) is None
    assert request.session == {}


@pytest.mark.parametrize("user_id", [None, "1", True, 0, -1, 999])
def test_require_authenticated_user_clears_stale_session_and_redirects(
    db: Session,
    user_id: object,
) -> None:
    request = _make_request({"user_id": user_id, "stale": "value"})

    with pytest.raises(HTTPException) as error:
        require_authenticated_user(request, db)

    assert request.session == {}
    assert error.value.status_code == status.HTTP_303_SEE_OTHER
    assert error.value.headers == {
        "Location": "/login",
        "Cache-Control": "no-store",
    }


def test_require_admin_returns_admin_user_id(db: Session) -> None:
    admin = create_user(
        db=db,
        username="admin",
        password_hash="test-hash",
        role=ADMIN_ROLE,
    )

    assert require_admin(_make_request({"user_id": admin.id}), db) == admin.id


def test_require_admin_rejects_non_admin(db: Session) -> None:
    user = create_user(
        db=db,
        username="regular-user",
        password_hash="test-hash",
    )

    with pytest.raises(HTTPException) as error:
        require_admin(_make_request({"user_id": user.id}), db)

    assert error.value.status_code == status.HTTP_403_FORBIDDEN
    assert error.value.detail == "접근 권한이 없습니다."


@pytest.mark.parametrize("user_id", [None, 999])
def test_require_admin_redirects_unauthenticated_user(
    db: Session,
    user_id: int | None,
) -> None:
    request = _make_request({} if user_id is None else {"user_id": user_id})

    with pytest.raises(HTTPException) as error:
        require_admin(request, db)

    assert request.session == {}
    assert error.value.status_code == status.HTTP_303_SEE_OTHER
    assert error.value.headers == {
        "Location": "/login",
        "Cache-Control": "no-store",
    }
