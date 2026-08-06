"""OpenAI context 구성 계약을 검증한다."""

from __future__ import annotations

import pytest

from app.chat.context import SYSTEM_PROMPT, build_context_messages
from app.chat.models import ChatExchange


def test_build_context_orders_history_oldest_first_and_appends_question() -> None:
    exchanges = [
        ChatExchange(question="new question", answer="new answer"),
        ChatExchange(question="old question", answer="old answer"),
    ]

    messages = build_context_messages(
        exchanges=exchanges,
        current_question="current question",
    )

    assert messages == [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "new question"},
        {"role": "assistant", "content": "new answer"},
        {"role": "user", "content": "current question"},
    ]


def test_build_context_rejects_history_without_answer() -> None:
    exchanges = [ChatExchange(question="failed question", answer=None)]

    with pytest.raises(ValueError, match="answer must not be None"):
        build_context_messages(exchanges=exchanges, current_question="current")
