"""Chat use case와 ChatExchange transaction을 처리한다."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import uuid4

from sqlalchemy.orm import Session

from app.chat.context import ChatMessage, build_context_messages
from app.chat.errors import (
    ChatGenerationError,
    ChatPersistenceError,
    ChatValidationError,
    ChatValidationReason,
)
from app.chat.models import ChatExchange
from app.chat.openai_client import (
    OpenAIAnswerGenerator,
    create_openai_client,
    get_openai_model,
)
from app.chat.repository import (
    ChatExchangeRepository,
    SqlAlchemyChatExchangeRepository,
)

CONTEXT_HISTORY_LIMIT = 5
MAX_MESSAGE_LENGTH = 1000

logger = logging.getLogger(__name__)


class AnswerGenerator(Protocol):
    """Chat Service가 사용하는 answer 생성 계약이다."""

    async def generate(self, *, messages: Sequence[ChatMessage]) -> str:
        """message 목록의 answer를 생성한다."""

        ...


@dataclass(frozen=True)
class ChatResult:
    """성공적으로 저장된 Chat 처리 결과다."""

    chat_exchange_id: int
    answer: str
    created_at: datetime


@dataclass(frozen=True)
class ChatExchangeHistoryItem:
    """사용자 화면에 안전하게 전달할 ChatExchange history 항목이다."""

    chat_exchange_id: int
    question: str
    answer: str | None
    status: str
    created_at: datetime


class ChatService:
    """질문 처리, answer 생성, ChatExchange 저장을 하나의 use case로 묶는다."""

    def __init__(
        self,
        *,
        db: Session,
        repository: ChatExchangeRepository,
        answer_generator: AnswerGenerator,
    ) -> None:
        self._db = db
        self._repository = repository
        self._answer_generator = answer_generator

    async def process_chat(
        self,
        *,
        user_id: int,
        message: str,
        request_id: str,
        user_agent: str | None,
    ) -> ChatResult:
        """질문을 처리하고 성공·실패 ChatExchange transaction을 완료한다."""

        started_at = time.perf_counter()
        question = _normalize_message(message)
        try:
            exchanges = self._repository.get_recent_success_exchanges(
                user_id=user_id,
                limit=CONTEXT_HISTORY_LIMIT,
            )
            messages = build_context_messages(
                exchanges=exchanges,
                current_question=question,
            )
            self._db.rollback()
        except Exception as error:
            self._db.rollback()
            raise ChatPersistenceError() from error

        try:
            answer = await self._answer_generator.generate(messages=messages)
        except ChatGenerationError as error:
            self._save_failed_exchange(
                user_id=user_id,
                question=question,
                error_message=error.record_message,
                request_id=request_id,
                user_agent=user_agent,
                response_time_ms=_elapsed_time_ms(started_at),
                error_code=error.record_message,
            )
            raise

        try:
            exchange = self._repository.create_success_exchange(
                user_id=user_id,
                question=question,
                answer=answer,
                request_id=request_id,
                user_agent=user_agent,
                response_time_ms=_elapsed_time_ms(started_at),
            )
            result = ChatResult(
                chat_exchange_id=exchange.id,
                answer=answer,
                created_at=exchange.created_at,
            )
            self._db.commit()
        except Exception as error:
            self._db.rollback()
            logger.error("db_save_failed")
            raise ChatPersistenceError() from error

        return result

    def _save_failed_exchange(
        self,
        *,
        user_id: int,
        question: str,
        error_message: str,
        request_id: str,
        user_agent: str | None,
        response_time_ms: int,
        error_code: str,
    ) -> None:
        try:
            self._repository.create_failed_exchange(
                user_id=user_id,
                question=question,
                error_message=error_message,
                request_id=request_id,
                user_agent=user_agent,
                response_time_ms=response_time_ms,
                error_code=error_code,
            )
            self._db.commit()
        except Exception as error:
            self._db.rollback()
            logger.error("db_save_failed")
            raise ChatPersistenceError() from error


async def process_chat(
    *,
    user_id: int,
    message: str,
    user_agent: str | None = None,
    db: Session,
) -> ChatResult:
    """production 의존성을 조립해 Chat use case를 실행한다."""

    normalized_message = _normalize_message(message)
    repository = SqlAlchemyChatExchangeRepository(db=db)
    async with create_openai_client() as client:
        service = ChatService(
            db=db,
            repository=repository,
            answer_generator=OpenAIAnswerGenerator(
                client=client,
                model=get_openai_model(),
            ),
        )
        return await service.process_chat(
            user_id=user_id,
            message=normalized_message,
            request_id=str(uuid4()),
            user_agent=user_agent,
        )


def list_chat_exchange_history(
    *,
    user_id: int,
    db: Session,
) -> list[ChatExchangeHistoryItem]:
    """로그인 사용자의 ChatExchange history를 내부 오류 없이 projection한다."""

    repository: ChatExchangeRepository = SqlAlchemyChatExchangeRepository(db=db)
    try:
        exchanges = repository.list_user_exchanges(user_id=user_id)
    except Exception as error:
        db.rollback()
        raise ChatPersistenceError() from error

    return [_to_history_item(exchange) for exchange in exchanges]


def _normalize_message(message: str) -> str:
    normalized = message.strip()
    if not normalized:
        raise ChatValidationError(ChatValidationReason.EMPTY_MESSAGE)
    if len(normalized) > MAX_MESSAGE_LENGTH:
        raise ChatValidationError(ChatValidationReason.MESSAGE_TOO_LONG)
    return normalized


def _elapsed_time_ms(started_at: float) -> int:
    return max(0, int((time.perf_counter() - started_at) * 1000))


def _to_history_item(exchange: ChatExchange) -> ChatExchangeHistoryItem:
    return ChatExchangeHistoryItem(
        chat_exchange_id=exchange.id,
        question=exchange.question,
        answer=exchange.answer,
        status=exchange.status,
        created_at=exchange.created_at,
    )
