"""Chat REST API의 request·response schema다."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator
from pydantic_core import PydanticCustomError

MAX_MESSAGE_LENGTH = 1000


class ChatRequest(BaseModel):
    """Chat 생성 요청이다."""

    message: StrictStr

    @field_validator("message")
    @classmethod
    def normalize_and_validate_message(cls, value: str) -> str:
        """공백을 제거한 질문이 허용 범위 안에 있는지 검증한다."""

        normalized = value.strip()
        if not normalized:
            raise PydanticCustomError("empty_message", "message must not be blank")
        if len(normalized) > MAX_MESSAGE_LENGTH:
            raise PydanticCustomError(
                "message_too_long",
                "message must be 1000 characters or fewer",
            )
        return normalized


class ChatResponse(BaseModel):
    """저장에 성공한 Chat 생성 응답이다."""

    model_config = ConfigDict(from_attributes=True)

    chat_exchange_id: int
    answer: str
    created_at: datetime


class ChatExchangeResponse(BaseModel):
    """사용자에게 노출 가능한 Chat history 항목이다."""

    model_config = ConfigDict(from_attributes=True)

    chat_exchange_id: int
    question: str
    answer: str | None
    status: str
    created_at: datetime


class ErrorResponse(BaseModel):
    """모든 JSON 오류가 공유하는 안정된 형태다."""

    code: str
    detail: str
