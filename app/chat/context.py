"""OpenAI 호출에 사용할 대화 문맥을 구성한다."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, TypedDict

from app.chat.models import Conversation


class ChatMessage(TypedDict):
    """OpenAI 대화 message의 최소 구조다."""

    role: Literal["user", "assistant"]
    content: str


def build_context_messages(
    *,
    conversations: Sequence[Conversation],
    current_question: str,
) -> list[ChatMessage]:
    """현재 질문을 포함한 OpenAI message 목록을 반환한다."""

    messages: list[ChatMessage] = []
    for conversation in reversed(conversations):
        if conversation.answer is None:
            raise ValueError("conversation answer must not be None")

        messages.append({"role": "user", "content": conversation.question})
        messages.append(
            {"role": "assistant", "content": conversation.answer}
        )

    messages.append({"role": "user", "content": current_question})
    return messages
