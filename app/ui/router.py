"""Render authentication and chat pages for browser clients."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AuthenticatedUser,
    clear_session_user_id,
    get_optional_authenticated_user,
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
from app.ui.responses import prevent_browser_caching
from app.ui.templating import templates

# Map registration failures to safe, user-facing messages.
_REGISTRATION_ERROR_MESSAGES = {
    RegistrationReason.USERNAME_LENGTH: "아이디는 3자 이상 30자 이하로 입력해주세요.",
    RegistrationReason.PASSWORD_LENGTH: "비밀번호는 8자 이상 72자 이하로 입력해주세요.",
    RegistrationReason.DUPLICATE_USERNAME: "이미 사용 중인 아이디입니다.",
}
# Avoid revealing which login credential was invalid.
_LOGIN_ERROR_MESSAGE = "아이디 또는 비밀번호가 올바르지 않습니다."

router = APIRouter()


@router.get("/", dependencies=[Depends(require_authenticated_user)])
def get_root() -> RedirectResponse:
    """Redirect an authenticated user to the chat page."""

    return _redirect_to("/chat")


@router.get("/signup", response_class=HTMLResponse)
def get_signup(
    request: Request,
    authenticated_user: Annotated[
        AuthenticatedUser | None,
        Depends(get_optional_authenticated_user),
    ],
) -> Response:
    """Render an empty signup form."""

    if authenticated_user is not None:
        return _redirect_to("/chat")
    return _render_auth_template(request, "signup.html")


@router.post("/signup", response_class=HTMLResponse)
def post_signup(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
) -> Response:
    """Register a user or render a safe signup error."""

    # Normalize usernames while preserving the password exactly as submitted.
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

    return _redirect_to("/login")


@router.get("/login", response_class=HTMLResponse)
def get_login(
    request: Request,
    authenticated_user: Annotated[
        AuthenticatedUser | None,
        Depends(get_optional_authenticated_user),
    ],
) -> Response:
    """Render an empty login form."""

    if authenticated_user is not None:
        return _redirect_to("/chat")
    return _render_auth_template(request, "login.html")


@router.post("/login", response_class=HTMLResponse)
def post_login(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
) -> Response:
    """Authenticate a user and establish the browser session."""

    # Normalize usernames while preserving the password exactly as submitted.
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
    return _redirect_to("/chat")


@router.post("/logout")
def post_logout(request: Request) -> RedirectResponse:
    """Clear the current session and redirect to the login page."""

    clear_session_user_id(request)
    return _redirect_to("/login")


@router.get("/chat", response_class=HTMLResponse)
def get_chat(
    request: Request,
    authenticated_user: Annotated[
        AuthenticatedUser,
        Depends(require_authenticated_user),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Render the authenticated user's chat history and input form."""

    chat_exchanges = list_chat_exchange_history(
        user_id=authenticated_user.user_id,
        db=db,
    )
    return prevent_browser_caching(
        templates.TemplateResponse(
            request=request,
            name="chat.html",
            context={
                "chat_exchanges": chat_exchanges,
                "is_admin": authenticated_user.is_admin,
            },
        )
    )


def _render_auth_template(
    request: Request,
    template_name: str,
    *,
    error: str | None = None,
    username: str = "",
    status_code: int = status.HTTP_200_OK,
) -> Response:
    """Render an authentication form with its safe display context."""

    return prevent_browser_caching(
        templates.TemplateResponse(
            request=request,
            name=template_name,
            context={"error": error, "username": username},
            status_code=status_code,
        )
    )


def _redirect_to(path: str) -> RedirectResponse:
    """Build the shared HTTP 303 redirect response."""

    return prevent_browser_caching(
        RedirectResponse(url=path, status_code=status.HTTP_303_SEE_OTHER)
    )
