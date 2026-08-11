"""인증과 관리자 권한을 확인하는 FastAPI dependency다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.models import ADMIN_ROLE
from app.auth.repository import get_user_by_id
from app.core.database import get_db

SESSION_USER_ID_KEY = "user_id"


@dataclass(frozen=True)
class AuthenticatedUser:
    """보호된 HTML 화면에 제공하는 최소 사용자 정보다."""

    user_id: int
    is_admin: bool


def set_session_user_id(request: Request, *, user_id: int) -> None:
    """Session을 login 사용자 ID 하나로 교체한다."""

    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id는 양의 정수여야 합니다.")
    request.session.clear()
    request.session[SESSION_USER_ID_KEY] = user_id


def get_session_user_id(request: Request) -> int | None:
    """Session의 유효한 login 사용자 ID를 반환한다."""

    user_id = request.session.get(SESSION_USER_ID_KEY)
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        return None
    return user_id


def clear_session_user_id(request: Request) -> None:
    """Logout을 위해 session data를 모두 제거한다."""

    request.session.clear()


def get_current_user_id(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> int:
    """보호된 JSON route에서 login 사용자의 ID를 반환한다."""

    user_id = get_session_user_id(request)
    if user_id is None:
        clear_session_user_id(request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다.",
        )

    if get_user_by_id(db=db, user_id=user_id) is None:
        clear_session_user_id(request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다.",
        )
    return user_id


def require_authenticated_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> AuthenticatedUser:
    """보호된 HTML 화면에 유효한 login 사용자 정보를 제공한다."""

    user_id = get_session_user_id(request)
    if user_id is None:
        clear_session_user_id(request)
        raise _login_redirect()

    user = get_user_by_id(db=db, user_id=user_id)
    if user is None:
        clear_session_user_id(request)
        raise _login_redirect()

    return AuthenticatedUser(
        user_id=user.id,
        is_admin=user.role == ADMIN_ROLE,
    )


def require_admin(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> int:
    """관리자 화면 접근을 허용하고 login 사용자 ID를 반환한다."""

    user_id = get_session_user_id(request)
    if user_id is None:
        raise _login_redirect()

    user = get_user_by_id(db=db, user_id=user_id)
    if user is None:
        raise _login_redirect()
    if user.role != ADMIN_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="접근 권한이 없습니다.",
        )
    return user_id


def _login_redirect() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Location": "/login"},
    )
