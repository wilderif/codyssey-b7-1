"""Chat Service review에서 확인된 regression을 검증한다."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.chat.service as service_module
from app.chat.context import ChatMessage
from app.chat.errors import ChatPersistenceError, ChatValidationError
from app.chat.models import ChatExchange
from app.chat.repository import SqlAlchemyChatExchangeRepository
from app.chat.service import (
    AnswerGenerator,
    ChatService,
    get_chat_exchange,
    list_chat_exchange_history,
)


class StaticAnswerGenerator:
    """외부 network 없이 고정 answer를 반환한다."""

    def __init__(self, answer: str = "answer") -> None:
        self.answer = answer

    async def generate(self, *, messages: Sequence[ChatMessage]) -> str:
        return self.answer


class TransactionCheckingGenerator:
    """OpenAI 호출 경계의 DB transaction 상태를 검증한다."""

    def __init__(self, db: Session) -> None:
        self._db = db

    async def generate(self, *, messages: Sequence[ChatMessage]) -> str:
        assert not self._db.in_transaction()
        return "answer"


class UnexpectedErrorGenerator:
    """예상하지 못한 programming error를 재현한다."""

    async def generate(self, *, messages: Sequence[ChatMessage]) -> str:
        raise RuntimeError("unexpected generator failure")


def create_service(db: Session, answer_generator: AnswerGenerator) -> ChatService:
    return ChatService(
        db=db,
        repository=SqlAlchemyChatExchangeRepository(db=db),
        answer_generator=answer_generator,
    )


@pytest.mark.parametrize(
    ("message", "expected_reason"),
    [
        ("   ", "empty_message"),
        ("x" * 1001, "message_too_long"),
    ],
)
def test_validation_error_identifies_the_invalid_rule(
    db: Session,
    user_id: int,
    message: str,
    expected_reason: str,
) -> None:
    service = create_service(db, StaticAnswerGenerator())

    with pytest.raises(ChatValidationError) as captured:
        asyncio.run(
            service.process_chat(
                user_id=user_id,
                message=message,
                request_id="validation-request",
                user_agent=None,
            )
        )

    assert captured.value.reason == expected_reason


def test_production_wrapper_validates_before_creating_openai_client(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    user_id: int,
) -> None:
    def fail_if_called() -> None:
        raise AssertionError("OpenAI client must not be created for invalid input")

    monkeypatch.setattr(service_module, "create_openai_client", fail_if_called)

    with pytest.raises(ChatValidationError) as captured:
        asyncio.run(
            service_module.process_chat(
                user_id=user_id,
                message=" ",
                user_agent=None,
                db=db,
            )
        )

    assert captured.value.reason == "empty_message"


def test_context_read_transaction_ends_before_answer_generation(
    db: Session,
    user_id: int,
) -> None:
    service = create_service(db, TransactionCheckingGenerator(db))

    result = asyncio.run(
        service.process_chat(
            user_id=user_id,
            message="question",
            request_id="transaction-request",
            user_agent=None,
        )
    )

    assert result.answer == "answer"


def test_unexpected_generator_error_is_not_reclassified_or_persisted(
    db: Session,
    user_id: int,
) -> None:
    service = create_service(db, UnexpectedErrorGenerator())

    with pytest.raises(RuntimeError, match="unexpected generator failure"):
        asyncio.run(
            service.process_chat(
                user_id=user_id,
                message="question",
                request_id="unexpected-error-request",
                user_agent=None,
            )
        )

    saved = db.scalar(select(ChatExchange).where(ChatExchange.question == "question"))
    assert saved is None


def test_success_does_not_start_a_new_transaction_after_commit(
    db: Session,
    user_id: int,
) -> None:
    service = create_service(db, StaticAnswerGenerator())

    result = asyncio.run(
        service.process_chat(
            user_id=user_id,
            message="question",
            request_id="success-transaction-request",
            user_agent=None,
        )
    )

    assert result.chat_exchange_id > 0
    assert not db.in_transaction()


class FailingSaveRepository(SqlAlchemyChatExchangeRepository):
    """저장 시도 횟수를 기록하고 첫 save를 실패시키는 repository다."""

    def __init__(self, *, db: Session) -> None:
        super().__init__(db=db)
        self.save_attempts = 0

    def create_success_exchange(
        self,
        *,
        user_id: int,
        question: str,
        answer: str,
        request_id: str,
        user_agent: str | None,
        response_time_ms: int,
    ) -> ChatExchange:
        self.save_attempts += 1
        raise RuntimeError("database save failed")


class FailingReadRepository(SqlAlchemyChatExchangeRepository):
    """모든 ChatExchange read를 실패시킨다."""

    def get_recent_success_exchanges(
        self, *, user_id: int, limit: int = 5
    ) -> list[ChatExchange]:
        raise RuntimeError("context read failed")

    def list_user_exchanges(self, *, user_id: int) -> list[ChatExchange]:
        raise RuntimeError("history list failed")

    def get_user_exchange(
        self, *, user_id: int, chat_exchange_id: int
    ) -> ChatExchange | None:
        raise RuntimeError("history item failed")


def _assert_read_failure(call: Callable[[], object]) -> None:
    with pytest.raises(ChatPersistenceError) as captured:
        call()

    assert captured.value.is_write is False


def test_context_read_failure_is_classified_as_non_write_error(
    db: Session,
    user_id: int,
) -> None:
    service = ChatService(
        db=db,
        repository=FailingReadRepository(db=db),
        answer_generator=StaticAnswerGenerator(),
    )

    _assert_read_failure(
        lambda: asyncio.run(
            service.process_chat(
                user_id=user_id,
                message="question",
                request_id="failing-context-read",
                user_agent=None,
            )
        )
    )


def test_history_list_read_failure_is_classified_as_non_write_error(
    db: Session,
    user_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service_module, "SqlAlchemyChatExchangeRepository", FailingReadRepository
    )

    _assert_read_failure(lambda: list_chat_exchange_history(user_id=user_id, db=db))


def test_single_history_read_failure_is_classified_as_non_write_error(
    db: Session,
    user_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service_module, "SqlAlchemyChatExchangeRepository", FailingReadRepository
    )

    _assert_read_failure(
        lambda: get_chat_exchange(user_id=user_id, chat_exchange_id=1, db=db)
    )


def test_save_failure_does_not_attempt_to_persist_another_failure_record(
    db: Session,
    user_id: int,
) -> None:
    repository = FailingSaveRepository(db=db)
    service = ChatService(
        db=db,
        repository=repository,
        answer_generator=StaticAnswerGenerator(),
    )

    with pytest.raises(ChatPersistenceError):
        asyncio.run(
            service.process_chat(
                user_id=user_id,
                message="question",
                request_id="save-failure-request",
                user_agent=None,
            )
        )

    assert repository.save_attempts == 1
    assert (
        db.scalar(select(ChatExchange).where(ChatExchange.question == "question"))
        is None
    )
