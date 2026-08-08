"""ChatExchange persistence repository다."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat.models import ChatExchange


class ChatExchangeRepository(Protocol):
    """Chat Service가 사용하는 ChatExchange persistence 계약이다."""

    def create_success_exchange(
        self,
        *,
        user_id: int,
        question: str,
        answer: str,
        request_id: str,
        user_agent: str | None,
        response_time_ms: int,
    ) -> ChatExchange:
        """성공 ChatExchange를 flush한다."""

        ...

    def create_failed_exchange(
        self,
        *,
        user_id: int,
        question: str,
        error_message: str,
        request_id: str,
        user_agent: str | None,
        response_time_ms: int,
        error_code: str,
    ) -> ChatExchange:
        """실패 ChatExchange를 flush한다."""

        ...

    def get_recent_success_exchanges(
        self,
        *,
        user_id: int,
        limit: int = 5,
    ) -> list[ChatExchange]:
        """사용자의 최근 성공 ChatExchange를 반환한다."""

        ...

    def list_user_exchanges(self, *, user_id: int) -> list[ChatExchange]:
        """사용자의 전체 ChatExchange history를 반환한다."""

        ...


class SqlAlchemyChatExchangeRepository:
    """SQLAlchemy Session을 사용하는 ChatExchangeRepository 구현체다."""

    def __init__(self, *, db: Session) -> None:
        self._db = db

    def create_success_exchange(
        self,
        *,
        user_id: int,
        question: str,
        answer: str,
        request_id: str,
        user_agent: str | None,
        response_time_ms: int,
    ) -> ChatExchange:
        return create_success_exchange(
            db=self._db,
            user_id=user_id,
            question=question,
            answer=answer,
            request_id=request_id,
            user_agent=user_agent,
            response_time_ms=response_time_ms,
        )

    def create_failed_exchange(
        self,
        *,
        user_id: int,
        question: str,
        error_message: str,
        request_id: str,
        user_agent: str | None,
        response_time_ms: int,
        error_code: str,
    ) -> ChatExchange:
        return create_failed_exchange(
            db=self._db,
            user_id=user_id,
            question=question,
            error_message=error_message,
            request_id=request_id,
            user_agent=user_agent,
            response_time_ms=response_time_ms,
            error_code=error_code,
        )

    def get_recent_success_exchanges(
        self,
        *,
        user_id: int,
        limit: int = 5,
    ) -> list[ChatExchange]:
        return get_recent_success_exchanges(
            db=self._db,
            user_id=user_id,
            limit=limit,
        )

    def list_user_exchanges(self, *, user_id: int) -> list[ChatExchange]:
        return list_user_exchanges(db=self._db, user_id=user_id)


def create_success_exchange(
    *,
    db: Session,
    user_id: int,
    question: str,
    answer: str,
    request_id: str,
    user_agent: str | None,
    response_time_ms: int,
) -> ChatExchange:
    """성공한 질문·답변 쌍을 flush한다."""

    exchange = ChatExchange(
        user_id=user_id,
        question=question,
        answer=answer,
        status="success",
        error_message=None,
        request_id=request_id,
        user_agent=user_agent,
        response_time_ms=response_time_ms,
        error_code=None,
    )
    db.add(exchange)
    db.flush()
    return exchange


def create_failed_exchange(
    *,
    db: Session,
    user_id: int,
    question: str,
    error_message: str,
    request_id: str,
    user_agent: str | None,
    response_time_ms: int,
    error_code: str,
) -> ChatExchange:
    """실패한 질문·답변 쌍을 flush한다."""

    exchange = ChatExchange(
        user_id=user_id,
        question=question,
        answer=None,
        status="failed",
        error_message=error_message,
        request_id=request_id,
        user_agent=user_agent,
        response_time_ms=response_time_ms,
        error_code=error_code,
    )
    db.add(exchange)
    db.flush()
    return exchange


def get_recent_success_exchanges(
    *,
    db: Session,
    user_id: int,
    limit: int = 5,
) -> list[ChatExchange]:
    """사용자의 최근 성공 ChatExchange를 반환한다."""

    if not 1 <= limit <= 5:
        raise ValueError("limit must be between 1 and 5")

    statement = (
        select(ChatExchange)
        .where(
            ChatExchange.user_id == user_id,
            ChatExchange.status == "success",
        )
        .order_by(ChatExchange.created_at.desc(), ChatExchange.id.desc())
        .limit(limit)
    )
    return list(db.scalars(statement))


def list_user_exchanges(*, db: Session, user_id: int) -> list[ChatExchange]:
    """사용자의 전체 ChatExchange history를 반환한다."""

    statement = (
        select(ChatExchange)
        .where(ChatExchange.user_id == user_id)
        .order_by(ChatExchange.created_at.desc(), ChatExchange.id.desc())
    )
    return list(db.scalars(statement))
