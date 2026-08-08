"""Chat REST API의 request·response schema다."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, StrictStr


class ChatRequest(BaseModel):
    """Chat 생성 요청이다."""

    message: StrictStr


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
