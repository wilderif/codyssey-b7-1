"""Chat domain의 SQLAlchemy model이다."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.core.database import Base


def utc_now() -> datetime:
    """UTC timezone 정보를 포함한 현재 시각을 반환한다."""

    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """SQLite에서도 UTC timezone 정보를 복원하는 datetime type이다."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self,
        value: datetime | None,
        dialect: object,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(UTC)

    def process_result_value(
        self,
        value: datetime | None,
        dialect: object,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class ChatExchange(Base):
    """사용자의 질문 처리 결과를 저장한다."""

    __tablename__ = "chat_exchanges"
    __table_args__ = (
        CheckConstraint(
            "(status = 'success' AND answer IS NOT NULL "
            "AND error_message IS NULL) OR "
            "(status = 'failed' AND answer IS NULL "
            "AND error_message IS NOT NULL)",
            name="ck_chat_exchanges_status_fields",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
    )
