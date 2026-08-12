"""Chat domain의 SQLAlchemy model이다."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_types import UTCDateTime, utc_now


class ChatExchange(Base):
    """사용자의 질문 처리 결과를 저장한다."""

    __tablename__ = "chat_exchanges"
    __table_args__ = (
        CheckConstraint(
            "(status = 'success' AND answer IS NOT NULL "
            "AND error_message IS NULL AND error_code IS NULL) OR "
            "(status = 'failed' AND answer IS NULL "
            "AND error_message IS NOT NULL AND error_code IS NOT NULL)",
            name="ck_chat_exchanges_status_fields",
        ),
        CheckConstraint(
            "length(request_id) <= 64",
            name="ck_chat_exchanges_request_id_length",
        ),
        CheckConstraint(
            "length(user_agent) <= 512",
            name="ck_chat_exchanges_user_agent_length",
        ),
        CheckConstraint(
            "response_time_ms >= 0",
            name="ck_chat_exchanges_response_time_ms_nonnegative",
        ),
        CheckConstraint(
            "length(error_code) <= 50",
            name="ck_chat_exchanges_error_code_length",
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
    request_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    response_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
