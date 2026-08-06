"""Chat domain이 HTTP layer에 전달하는 안전한 오류다."""

from __future__ import annotations

from enum import StrEnum


class ChatError(Exception):
    """사용자 응답으로 변환 가능한 Chat domain 오류의 base class다."""


class ChatValidationReason(StrEnum):
    """질문이 위반한 Chat domain validation 규칙이다."""

    EMPTY_MESSAGE = "empty_message"
    MESSAGE_TOO_LONG = "message_too_long"


class ChatValidationError(ChatError):
    """질문이 Chat domain 규칙을 만족하지 않는다."""

    def __init__(self, reason: ChatValidationReason) -> None:
        self.reason = reason
        super().__init__(reason.value)


class ChatGenerationError(ChatError):
    """OpenAI 답변을 생성하지 못했다."""

    record_message = "openai_api_error"


class ChatTimeoutError(ChatGenerationError):
    """OpenAI 호출 시간이 초과됐다."""

    record_message = "openai_timeout"


class ChatInvalidResponseError(ChatGenerationError):
    """OpenAI response에 사용할 수 있는 text answer가 없다."""

    record_message = "openai_invalid_response"


class ChatConfigurationError(ChatError):
    """OpenAI 호출에 필요한 server 설정이 없다."""


class ChatPersistenceError(ChatError):
    """ChatExchange 조회 또는 저장 transaction이 실패했다."""
