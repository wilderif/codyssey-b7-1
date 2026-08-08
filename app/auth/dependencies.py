"""인증과 관리자 권한을 확인하는 FastAPI dependency다."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.models import ADMIN_ROLE
from app.auth.repository import get_user_by_id
from app.core.database import get_db

SESSION_USER_ID_KEY = "user_id"


def get_current_user_id(request: Request) -> int:
    """보호된 JSON route에서 login 사용자의 ID를 반환한다."""

    user_id = _get_session_user_id(request)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다.",
        )
    return user_id


def require_admin(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> int:
    """관리자 화면 접근을 허용하고 login 사용자 ID를 반환한다."""

    user_id = _get_session_user_id(request)
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


def _get_session_user_id(request: Request) -> int | None:
    user_id = request.session.get(SESSION_USER_ID_KEY)
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        return None
    return user_id


def _login_redirect() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Location": "/login"},
    )
