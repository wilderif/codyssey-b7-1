"""로그인 사용자의 Chat JSON API HTTP layer다."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.exception_handlers import (
    http_exception_handler as default_http_exception_handler,
)
from fastapi.exception_handlers import (
    request_validation_exception_handler as default_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user_id
from app.chat.errors import (
    AppError,
    ChatGenerationError,
    ChatPersistenceError,
    ChatTimeoutError,
    ChatValidationError,
    ChatValidationReason,
)
from app.chat.i18n import get_message
from app.chat.schemas import (
    ChatExchangeResponse,
    ChatRequest,
    ChatResponse,
    ErrorResponse,
)
from app.chat.service import get_chat_exchange, list_chat_exchange_history, process_chat
from app.core.database import get_db
from app.core.request_id import REQUEST_ID_HEADER, get_request_id

router = APIRouter()


@router.post(
    "/api/chat",
    response_model=ChatResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
)
async def post_chat(
    payload: ChatRequest,
    request: Request,
    user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
) -> ChatResponse:
    """질문을 처리하고 저장이 완료된 answer를 반환한다."""

    try:
        result = await process_chat(
            user_id=user_id,
            message=payload.message,
            request_id=get_request_id(request),
            user_agent=_normalize_user_agent(request.headers.get("user-agent")),
            db=db,
        )
    except ChatValidationError as error:
        raise _validation_app_error(error) from error
    except ChatTimeoutError as error:
        raise AppError(status_code=504, code="openai_timeout") from error
    except ChatGenerationError as error:
        raise AppError(status_code=502, code="openai_api_error") from error
    except ChatPersistenceError as error:
        raise _persistence_app_error(error) from error

    return ChatResponse.model_validate(result)


@router.get(
    "/api/chat-exchanges",
    response_model=list[ChatExchangeResponse],
    responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
def get_chat_exchanges(
    user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ChatExchangeResponse]:
    """로그인 사용자의 전체 대화 기록을 최신순으로 반환한다."""

    try:
        return [
            ChatExchangeResponse.model_validate(item)
            for item in list_chat_exchange_history(user_id=user_id, db=db)
        ]
    except ChatPersistenceError as error:
        raise _persistence_app_error(error) from error


@router.get(
    "/api/chat-exchanges/{chat_exchange_id}",
    response_model=ChatExchangeResponse,
    responses={
        401: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def get_chat_exchange_by_id(
    chat_exchange_id: int,
    user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
) -> ChatExchangeResponse:
    """로그인 사용자가 소유한 단일 대화 기록을 반환한다."""

    try:
        exchange = get_chat_exchange(
            user_id=user_id,
            chat_exchange_id=chat_exchange_id,
            db=db,
        )
    except ChatPersistenceError as error:
        raise _persistence_app_error(error) from error
    if exchange is None:
        raise AppError(status_code=404, code="conversation_not_found")
    return ChatExchangeResponse.model_validate(exchange)


async def app_error_handler(request: Request, error: Exception) -> Response:
    """AppError를 locale-aware JSON 오류로 변환한다."""

    if not isinstance(error, AppError):
        return await unhandled_exception_handler(request, error)
    return _error_response(
        request=request,
        status_code=error.status_code,
        code=error.code,
        detail_key=error.detail_key,
    )


async def validation_exception_handler(request: Request, _error: Exception) -> Response:
    """Pydantic body 검증 실패를 내부 구조 없이 통일한다."""

    if not request.url.path.startswith("/api/"):
        if isinstance(_error, RequestValidationError):
            return await default_validation_exception_handler(request, _error)
        return await unhandled_exception_handler(request, _error)
    return _error_response(request=request, status_code=422, code="validation_error")


async def http_exception_handler(request: Request, error: Exception) -> Response:
    """Auth dependency의 HTTPException도 JSON API 오류 형식으로 통일한다."""

    if not isinstance(error, HTTPException):
        return await unhandled_exception_handler(request, error)
    if not request.url.path.startswith("/api/"):
        return await default_http_exception_handler(request, error)
    if error.status_code == status.HTTP_401_UNAUTHORIZED:
        return _error_response(
            request=request, status_code=401, code="not_authenticated"
        )
    if error.status_code == status.HTTP_403_FORBIDDEN:
        return _error_response(request=request, status_code=403, code="forbidden")
    return _error_response(request=request, status_code=500, code="internal_error")


async def unhandled_exception_handler(request: Request, _error: Exception) -> Response:
    """예상하지 못한 예외를 안전한 내부 오류로 변환한다."""

    if not request.url.path.startswith("/api/"):
        raise _error
    response = _error_response(
        request=request,
        status_code=500,
        code="internal_error",
    )
    response.headers[REQUEST_ID_HEADER] = get_request_id(request)
    return response


def _validation_app_error(error: ChatValidationError) -> AppError:
    detail_key = {
        ChatValidationReason.EMPTY_MESSAGE: "empty_message",
        ChatValidationReason.MESSAGE_TOO_LONG: "message_too_long",
    }[error.reason]
    return AppError(status_code=400, code="validation_error", detail_key=detail_key)


def _persistence_app_error(error: ChatPersistenceError) -> AppError:
    """저장 실패만 db_save_error로, 조회 실패는 internal_error로 변환한다."""

    code = "db_save_error" if error.is_write else "internal_error"
    return AppError(status_code=500, code=code)


def _normalize_user_agent(user_agent: str | None) -> str | None:
    """운영 metadata column 길이 안에서 User-Agent를 보관한다."""

    return user_agent[:512] if user_agent is not None else None


def _error_response(
    *,
    request: Request,
    status_code: int,
    code: str,
    detail_key: str | None = None,
) -> JSONResponse:
    detail = get_message(
        key=detail_key or code,
        accept_language=request.headers.get("accept-language"),
    )
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(code=code, detail=detail).model_dump(),
    )
