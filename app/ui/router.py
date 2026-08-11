"""Server-rendered 인증 화면의 HTTP layer다."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AuthenticatedUser,
    clear_session_user_id,
    require_authenticated_user,
    set_session_user_id,
)
from app.auth.service import (
    RegistrationError,
    RegistrationReason,
    authenticate_user,
    register_user,
)
from app.chat.service import list_chat_exchange_history
from app.core.database import get_db

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

_REGISTRATION_ERROR_MESSAGES = {
    RegistrationReason.USERNAME_LENGTH: "아이디는 3자 이상 30자 이하로 입력해주세요.",
    RegistrationReason.PASSWORD_LENGTH: "비밀번호는 8자 이상 72자 이하로 입력해주세요.",
    RegistrationReason.DUPLICATE_USERNAME: "이미 사용 중인 아이디입니다.",
}
_LOGIN_ERROR_MESSAGE = "아이디 또는 비밀번호가 올바르지 않습니다."


@router.get("/", dependencies=[Depends(require_authenticated_user)])
def get_root() -> RedirectResponse:
    """유효한 login 사용자를 Chat 화면으로 이동시킨다."""

    return RedirectResponse(url="/chat", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/signup", response_class=HTMLResponse)
def get_signup(request: Request) -> Response:
    """빈 회원가입 form을 제공한다."""

    return _render_auth_template(request, "signup.html")


@router.post("/signup", response_class=HTMLResponse)
def post_signup(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
) -> Response:
    """회원가입 form을 처리하고 Login 화면으로 이동시킨다."""

    username = username.strip()
    try:
        register_user(
            db=db,
            username=username,
            password=password,
        )
    except RegistrationError as error:
        return _render_auth_template(
            request=request,
            template_name="signup.html",
            error=_REGISTRATION_ERROR_MESSAGES[error.reason],
            username=username,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login", response_class=HTMLResponse)
def get_login(request: Request) -> Response:
    """빈 Login form을 제공한다."""

    return _render_auth_template(request, "login.html")


@router.post("/login", response_class=HTMLResponse)
def post_login(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
) -> Response:
    """Login form을 검증하고 성공한 사용자 Session을 생성한다."""

    username = username.strip()
    user = authenticate_user(
        db=db,
        username=username,
        password=password,
    )
    if user is None:
        return _render_auth_template(
            request=request,
            template_name="login.html",
            error=_LOGIN_ERROR_MESSAGE,
            username=username,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    set_session_user_id(request, user_id=user.id)
    return RedirectResponse(url="/chat", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def post_logout(request: Request) -> RedirectResponse:
    """현재 Session을 제거하고 Login 화면으로 이동시킨다."""

    clear_session_user_id(request)
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/chat", response_class=HTMLResponse)
def get_chat(
    request: Request,
    authenticated_user: Annotated[
        AuthenticatedUser,
        Depends(require_authenticated_user),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """로그인 사용자의 이전 대화와 Chat 입력 화면을 제공한다."""

    chat_exchanges = list_chat_exchange_history(
        user_id=authenticated_user.user_id,
        db=db,
    )
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "chat_exchanges": chat_exchanges,
            "is_admin": authenticated_user.is_admin,
        },
    )


def _render_auth_template(
    request: Request,
    template_name: str,
    *,
    error: str | None = None,
    username: str = "",
    status_code: int = status.HTTP_200_OK,
) -> Response:
    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context={"error": error, "username": username},
        status_code=status_code,
    )
