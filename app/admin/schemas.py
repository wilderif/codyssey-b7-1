"""관리자 화면에 전달하는 안전한 read model schema다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AdminChatOperationMetadataItem:
    """관리자 화면용 ChatExchange 운영 metadata다."""

    user_id: int
    username: str | None
    chat_exchange_id: int
    created_at: datetime
    request_id: str
    user_agent: str | None
    response_time_ms: int
    status: str
    error_code: str | None
