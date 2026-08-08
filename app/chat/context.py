"""OpenAI 호출에 사용할 대화 문맥을 구성한다."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, TypedDict

from app.chat.models import ChatExchange

SYSTEM_PROMPT = (
    "You are a helpful assistant. "
    "Answer clearly and concisely in the user's language. "
    "Use plain text only and do not use Markdown formatting."
)


class ChatMessage(TypedDict):
    """OpenAI 대화 message의 최소 구조다."""

    role: Literal["system", "user", "assistant"]
    content: str


def build_context_messages(
    *,
    exchanges: Sequence[ChatExchange],
    current_question: str,
) -> list[ChatMessage]:
    """현재 질문을 포함한 OpenAI message 목록을 반환한다."""

    messages: list[ChatMessage] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for exchange in reversed(exchanges):
        if exchange.answer is None:
            raise ValueError("chat exchange answer must not be None")

        messages.append({"role": "user", "content": exchange.question})
        messages.append({"role": "assistant", "content": exchange.answer})

    messages.append({"role": "user", "content": current_question})
    return messages
