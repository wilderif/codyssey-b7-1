"""Chat Service의 성공·실패 transaction과 history 계약을 검증한다."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.chat.context import SYSTEM_PROMPT, ChatMessage
from app.chat.errors import (
    ChatGenerationError,
    ChatInvalidResponseError,
    ChatPersistenceError,
    ChatTimeoutError,
)
from app.chat.models import ChatExchange
from app.chat.repository import SqlAlchemyChatExchangeRepository
from app.chat.service import ChatService, list_chat_exchange_history


class RecordingGenerator:
    def __init__(
        self,
        *,
        answer: str = "answer",
        error: ChatGenerationError | None = None,
    ) -> None:
        self.answer = answer
        self.error = error
        self.messages: list[list[ChatMessage]] = []

    async def generate(self, *, messages: Sequence[ChatMessage]) -> str:
        self.messages.append(list(messages))
        if self.error is not None:
            raise self.error
        return self.answer


def create_service(db: Session, generator: RecordingGenerator) -> ChatService:
    return ChatService(
        db=db,
        repository=SqlAlchemyChatExchangeRepository(db=db),
        answer_generator=generator,
    )


def test_success_uses_recent_success_context_and_persists_trimmed_question(
    db: Session,
    user_id: int,
) -> None:
    other = User(username="context-other", password_hash="hash")
    db.add(other)
    db.flush()
    base_time = datetime(2026, 8, 6, tzinfo=UTC)
    for index in range(6):
        db.add(
            ChatExchange(
                user_id=user_id,
                question=f"q{index}",
                answer=f"a{index}",
                status="success",
                error_message=None,
                created_at=base_time + timedelta(minutes=index),
            )
        )
    db.add_all(
        [
            ChatExchange(
                user_id=user_id,
                question="failed",
                answer=None,
                status="failed",
                error_message="openai_timeout",
                created_at=base_time + timedelta(hours=1),
            ),
            ChatExchange(
                user_id=other.id,
                question="other",
                answer="other answer",
                status="success",
                error_message=None,
                created_at=base_time + timedelta(hours=2),
            ),
        ]
    )
    db.commit()
    generator = RecordingGenerator(answer="generated answer")
    service = create_service(db, generator)

    result = asyncio.run(
        service.process_chat(user_id=user_id, message="  current question  ")
    )

    assert generator.messages == [
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "q3"},
            {"role": "assistant", "content": "a3"},
            {"role": "user", "content": "q4"},
            {"role": "assistant", "content": "a4"},
            {"role": "user", "content": "q5"},
            {"role": "assistant", "content": "a5"},
            {"role": "user", "content": "current question"},
        ]
    ]
    saved = db.get(ChatExchange, result.chat_exchange_id)
    assert saved is not None
    assert (saved.question, saved.answer, saved.status, saved.error_message) == (
        "current question",
        "generated answer",
        "success",
        None,
    )


@pytest.mark.parametrize(
    ("error", "record_message"),
    [
        (ChatGenerationError(), "openai_api_error"),
        (ChatTimeoutError(), "openai_timeout"),
        (ChatInvalidResponseError(), "openai_invalid_response"),
    ],
)
def test_generation_error_persists_safe_failure_and_propagates(
    db: Session,
    user_id: int,
    error: ChatGenerationError,
    record_message: str,
) -> None:
    service = create_service(db, RecordingGenerator(error=error))

    with pytest.raises(type(error)):
        asyncio.run(service.process_chat(user_id=user_id, message="question"))

    saved = db.scalar(select(ChatExchange).where(ChatExchange.question == "question"))
    assert saved is not None
    assert (saved.answer, saved.status, saved.error_message) == (
        None,
        "failed",
        record_message,
    )


def test_success_commit_failure_rolls_back_and_raises_persistence_error(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    user_id: int,
) -> None:
    service = create_service(db, RecordingGenerator())

    def fail_commit() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db, "commit", fail_commit)

    with pytest.raises(ChatPersistenceError):
        asyncio.run(service.process_chat(user_id=user_id, message="question"))

    assert not db.in_transaction()


def test_failed_record_commit_failure_takes_priority_over_generation_error(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    user_id: int,
) -> None:
    service = create_service(db, RecordingGenerator(error=ChatTimeoutError()))

    def fail_commit() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db, "commit", fail_commit)

    with pytest.raises(ChatPersistenceError):
        asyncio.run(service.process_chat(user_id=user_id, message="question"))

    assert not db.in_transaction()


def test_history_projection_is_user_scoped_and_omits_internal_error(
    db: Session,
    user_id: int,
) -> None:
    other = User(username="history-other", password_hash="hash")
    db.add(other)
    db.flush()
    db.add_all(
        [
            ChatExchange(
                user_id=user_id,
                question="mine",
                answer=None,
                status="failed",
                error_message="openai_api_error",
            ),
            ChatExchange(
                user_id=other.id,
                question="other",
                answer="other answer",
                status="success",
                error_message=None,
            ),
        ]
    )
    db.commit()

    history = list_chat_exchange_history(user_id=user_id, db=db)

    assert len(history) == 1
    assert history[0].question == "mine"
    assert not hasattr(history[0], "error_message")
