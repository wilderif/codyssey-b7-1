"""FastAPI application의 공통 실행 구성을 조립한다."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.middleware.sessions import SessionMiddleware

from app.admin.router import router as admin_router
from app.auth.models import User
from app.chat.errors import AppError
from app.chat.models import ChatExchange
from app.chat.router import (
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.chat.router import router as chat_router
from app.core.config import Settings, settings
from app.core.database import init_db
from app.core.request_id import RequestIdMiddleware

SESSION_MAX_AGE_SECONDS = 28_800
_REGISTERED_MODELS = (User, ChatExchange)


@asynccontextmanager
async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
    """요청을 받기 전에 application DB table을 초기화한다."""

    init_db()
    yield


def create_app(app_settings: Settings | None = None) -> FastAPI:
    """검증된 설정으로 FastAPI application을 생성한다."""

    configured = app_settings or settings
    session_secret = _require_session_secret(configured)
    _configure_logging(configured.log_level)

    application = FastAPI(lifespan=lifespan)
    application.add_middleware(
        SessionMiddleware,
        secret_key=session_secret,
        max_age=SESSION_MAX_AGE_SECONDS,
        same_site="lax",
        https_only=configured.app_env == "production",
    )
    application.add_middleware(RequestIdMiddleware)

    application.include_router(admin_router)
    application.include_router(chat_router)
    application.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,
    )
    application.add_exception_handler(AppError, app_error_handler)
    application.add_exception_handler(HTTPException, http_exception_handler)
    application.add_exception_handler(Exception, unhandled_exception_handler)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


def _require_session_secret(app_settings: Settings) -> str:
    secret = app_settings.session_secret
    if secret is None or not secret.get_secret_value().strip():
        raise RuntimeError("SESSION_SECRET environment variable이 필요합니다.")
    return secret.get_secret_value()


def _configure_logging(log_level: str) -> None:
    level = getattr(logging, log_level)
    logging.basicConfig(level=level)
    logging.getLogger().setLevel(level)


app = create_app()
