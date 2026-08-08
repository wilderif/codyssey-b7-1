"""관리자 운영 metadata read repository다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.chat.models import ChatExchange


@dataclass(frozen=True)
class AdminChatOperationMetadataRow:
    """관리자 Service 내부에서 사용하는 최소 read row다."""

    user_id: int
    username: str | None
    chat_exchange_id: int
    created_at: datetime
    request_id: str
    user_agent: str | None
    response_time_ms: int
    status: str
    error_code: str | None


class AdminRepository(Protocol):
    """관리자 read use case의 persistence contract다."""

    def list_chat_operation_metadata(self) -> list[AdminChatOperationMetadataRow]:
        """안전한 ChatExchange 운영 metadata row를 최신순으로 반환한다."""

        ...


class SqlAlchemyAdminRepository:
    """SQLAlchemy Session으로 관리자 read query를 실행한다."""

    def __init__(self, *, db: Session) -> None:
        self._db = db

    def list_chat_operation_metadata(self) -> list[AdminChatOperationMetadataRow]:
        statement = (
            select(
                ChatExchange.user_id,
                User.username,
                ChatExchange.id,
                ChatExchange.created_at,
                ChatExchange.request_id,
                ChatExchange.user_agent,
                ChatExchange.response_time_ms,
                ChatExchange.status,
                ChatExchange.error_code,
            )
            .select_from(ChatExchange)
            .outerjoin(User, ChatExchange.user_id == User.id)
            .order_by(ChatExchange.created_at.desc(), ChatExchange.id.desc())
        )
        return [
            AdminChatOperationMetadataRow(
                user_id=user_id,
                username=username,
                chat_exchange_id=chat_exchange_id,
                created_at=created_at,
                request_id=request_id,
                user_agent=user_agent,
                response_time_ms=response_time_ms,
                status=status,
                error_code=error_code,
            )
            for (
                user_id,
                username,
                chat_exchange_id,
                created_at,
                request_id,
                user_agent,
                response_time_ms,
                status,
                error_code,
            ) in self._db.execute(statement)
        ]
