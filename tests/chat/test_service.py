"""Chat Service의 성공·실패 transaction과 history 계약을 검증한다."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.chat.service as service_module
from app.auth.models import User
from app.chat.context import SYSTEM_PROMPT, ChatMessage
from app.chat.errors import (
    ChatConfigurationError,
    ChatGenerationError,
    ChatInvalidResponseError,
    ChatPersistenceError,
    ChatTimeoutError,
    ChatValidationError,
)
from app.chat.models import ChatExchange
from app.chat.repository import SqlAlchemyChatExchangeRepository
from app.chat.service import (
    AnswerGenerator,
    ChatService,
    get_chat_exchange,
    list_chat_exchange_history,
)


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


class FailingSaveRepository(SqlAlchemyChatExchangeRepository):
    """성공 record 저장 시도 횟수를 기록하고 실패시킨다."""

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
        raise RuntimeError("SELECT stack api-key Cookie internal error_message")


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


def _create_service(db: Session, generator: AnswerGenerator) -> ChatService:
    return ChatService(
        db=db,
        repository=SqlAlchemyChatExchangeRepository(db=db),
        answer_generator=generator,
    )


def _service_log_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records]


def _assert_safe_request_id_logs(
    messages: list[str], *, request_id: str, expected_events: set[str]
) -> None:
    assert {
        message.split(" request_id=", maxsplit=1)[0] for message in messages
    } == expected_events
    assert all(f"request_id={request_id}" in message for message in messages)
    log_text = "\n".join(messages).lower()
    for secret in (
        "select",
        "stack",
        "key",
        "cookie",
        "internal error_message",
    ):
        assert secret not in log_text


def _assert_read_failure(call: Callable[[], object]) -> None:
    with pytest.raises(ChatPersistenceError) as captured:
        call()

    assert captured.value.is_write is False


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
    service = _create_service(db, RecordingGenerator())

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


def test_context_read_transaction_ends_before_answer_generation(
    db: Session,
    user_id: int,
) -> None:
    service = _create_service(db, TransactionCheckingGenerator(db))

    result = asyncio.run(
        service.process_chat(
            user_id=user_id,
            message="question",
            request_id="transaction-request",
            user_agent=None,
        )
    )

    assert result.answer == "answer"


def test_context_read_failure_is_classified_as_non_write_error(
    db: Session,
    user_id: int,
) -> None:
    service = ChatService(
        db=db,
        repository=FailingReadRepository(db=db),
        answer_generator=RecordingGenerator(),
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


def test_success_uses_recent_success_context_and_persists_trimmed_question(
    db: Session,
    user_id: int,
    caplog: pytest.LogCaptureFixture,
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
                request_id=f"context-success-{index}",
                user_agent=None,
                response_time_ms=1,
                error_code=None,
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
                request_id="context-failed",
                user_agent=None,
                response_time_ms=1,
                error_code="openai_timeout",
                created_at=base_time + timedelta(hours=1),
            ),
            ChatExchange(
                user_id=other.id,
                question="other",
                answer="other answer",
                status="success",
                error_message=None,
                request_id="context-other",
                user_agent=None,
                response_time_ms=1,
                error_code=None,
                created_at=base_time + timedelta(hours=2),
            ),
        ]
    )
    db.commit()
    generator = RecordingGenerator(answer="generated answer")
    service = _create_service(db, generator)
    question = "SELECT stack api-key Cookie internal error_message"
    request_id = "success-request"

    with caplog.at_level("INFO", logger="app.chat.service"):
        result = asyncio.run(
            service.process_chat(
                user_id=user_id,
                message=f"  {question}  ",
                request_id=request_id,
                user_agent="Cookie secret",
            )
        )

    assert not db.in_transaction()

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
            {"role": "user", "content": question},
        ]
    ]
    saved = db.get(ChatExchange, result.chat_exchange_id)
    assert saved is not None
    assert (
        saved.question,
        saved.answer,
        saved.status,
        saved.error_message,
        saved.request_id,
        saved.user_agent,
        saved.response_time_ms >= 0,
        saved.error_code,
    ) == (
        question,
        "generated answer",
        "success",
        None,
        request_id,
        "Cookie secret",
        True,
        None,
    )
    _assert_safe_request_id_logs(
        _service_log_messages(caplog),
        request_id=request_id,
        expected_events={
            "request_received",
            "ai_call_started",
            "ai_call_succeeded",
            "db_save_succeeded",
        },
    )


@pytest.mark.parametrize(
    ("error", "record_message"),
    [
        (ChatGenerationError(), "openai_api_error"),
        (ChatTimeoutError(), "openai_timeout"),
        (ChatInvalidResponseError(), "openai_api_error"),
    ],
)
def test_generation_error_persists_safe_failure_and_propagates(
    db: Session,
    user_id: int,
    caplog: pytest.LogCaptureFixture,
    error: ChatGenerationError,
    record_message: str,
) -> None:
    service = _create_service(db, RecordingGenerator(error=error))
    request_id = f"failure-request-{record_message}"

    with (
        caplog.at_level("INFO", logger="app.chat.service"),
        pytest.raises(type(error)),
    ):
        asyncio.run(
            service.process_chat(
                user_id=user_id,
                message="question",
                request_id=request_id,
                user_agent=None,
            )
        )

    saved = db.scalar(select(ChatExchange).where(ChatExchange.question == "question"))
    assert saved is not None
    assert (saved.answer, saved.status, saved.error_message, saved.error_code) == (
        None,
        "failed",
        record_message,
        record_message,
    )
    _assert_safe_request_id_logs(
        _service_log_messages(caplog),
        request_id=request_id,
        expected_events={
            "request_received",
            "ai_call_started",
            "ai_call_failed",
            "db_save_succeeded",
        },
    )


def test_unexpected_generator_error_persists_internal_failure_and_propagates(
    db: Session,
    user_id: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = _create_service(db, UnexpectedErrorGenerator())

    with (
        caplog.at_level("INFO", logger="app.chat.service"),
        pytest.raises(RuntimeError, match="unexpected generator failure"),
    ):
        asyncio.run(
            service.process_chat(
                user_id=user_id,
                message="question",
                request_id="unexpected-error-request",
                user_agent="test-agent/1.0",
            )
        )

    saved = db.scalar(select(ChatExchange).where(ChatExchange.question == "question"))
    assert saved is not None
    assert (
        saved.answer,
        saved.status,
        saved.error_message,
        saved.error_code,
        saved.request_id,
        saved.user_agent,
    ) == (
        None,
        "failed",
        "internal_error",
        "internal_error",
        "unexpected-error-request",
        "test-agent/1.0",
    )
    assert (
        "ai_call_failed request_id=unexpected-error-request code=internal_error"
        in caplog.text
    )


def test_success_commit_failure_rolls_back_and_raises_persistence_error(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    user_id: int,
) -> None:
    service = _create_service(db, RecordingGenerator())

    def fail_commit() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db, "commit", fail_commit)

    with pytest.raises(ChatPersistenceError):
        asyncio.run(
            service.process_chat(
                user_id=user_id,
                message="question",
                request_id="success-commit-failure",
                user_agent=None,
            )
        )

    assert not db.in_transaction()


def test_save_failure_does_not_persist_failure_record_and_logs_safely(
    db: Session,
    user_id: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = FailingSaveRepository(db=db)
    service = ChatService(
        db=db,
        repository=repository,
        answer_generator=RecordingGenerator(),
    )
    request_id = "save-failure-request"

    with (
        caplog.at_level("INFO", logger="app.chat.service"),
        pytest.raises(ChatPersistenceError),
    ):
        asyncio.run(
            service.process_chat(
                user_id=user_id,
                message="question",
                request_id=request_id,
                user_agent=None,
            )
        )

    assert repository.save_attempts == 1
    assert (
        db.scalar(select(ChatExchange).where(ChatExchange.question == "question"))
        is None
    )
    _assert_safe_request_id_logs(
        _service_log_messages(caplog),
        request_id=request_id,
        expected_events={
            "request_received",
            "ai_call_started",
            "ai_call_succeeded",
            "db_save_failed",
        },
    )


def test_failed_record_commit_failure_takes_priority_over_generation_error(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    user_id: int,
) -> None:
    service = _create_service(db, RecordingGenerator(error=ChatTimeoutError()))

    def fail_commit() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db, "commit", fail_commit)

    with pytest.raises(ChatPersistenceError):
        asyncio.run(
            service.process_chat(
                user_id=user_id,
                message="question",
                request_id="failed-commit-failure",
                user_agent=None,
            )
        )

    assert not db.in_transaction()


def test_production_wrapper_validates_and_logs_before_creating_openai_client(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    user_id: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail_if_called() -> None:
        raise AssertionError("OpenAI client must not be created for invalid input")

    monkeypatch.setattr(service_module, "create_openai_client", fail_if_called)

    with (
        caplog.at_level("INFO", logger="app.chat.service"),
        pytest.raises(ChatValidationError) as captured,
    ):
        asyncio.run(
            service_module.process_chat(
                user_id=user_id,
                message=" ",
                request_id="production-validation-request",
                user_agent="Cookie secret",
                db=db,
            )
        )

    assert captured.value.reason == "empty_message"
    assert _service_log_messages(caplog) == [
        "request_received request_id=production-validation-request"
    ]


def test_production_wrapper_logs_safely_before_client_configuration_failure(
    db: Session,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_client_creation() -> object:
        raise ChatConfigurationError()

    monkeypatch.setattr(service_module, "create_openai_client", fail_client_creation)

    with (
        caplog.at_level("INFO", logger="app.chat.service"),
        pytest.raises(ChatConfigurationError),
    ):
        asyncio.run(
            service_module.process_chat(
                user_id=1,
                message="SELECT stack api-key Cookie internal error_message",
                request_id="wrapper-config-id",
                user_agent="Cookie secret",
                db=db,
            )
        )

    _assert_safe_request_id_logs(
        _service_log_messages(caplog),
        request_id="wrapper-config-id",
        expected_events={"request_received"},
    )


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
                request_id="history-mine",
                user_agent=None,
                response_time_ms=1,
                error_code="openai_api_error",
            ),
            ChatExchange(
                user_id=other.id,
                question="other",
                answer="other answer",
                status="success",
                error_message=None,
                request_id="history-other",
                user_agent=None,
                response_time_ms=1,
                error_code=None,
            ),
        ]
    )
    db.commit()

    history = list_chat_exchange_history(user_id=user_id, db=db)

    assert len(history) == 1
    assert history[0].question == "mine"
    assert not hasattr(history[0], "error_message")


@pytest.mark.parametrize(
    ("read_history", "extra_arguments"),
    [
        (list_chat_exchange_history, {}),
        (get_chat_exchange, {"chat_exchange_id": 1}),
    ],
)
def test_history_read_failures_are_classified_as_non_write_errors(
    db: Session,
    user_id: int,
    monkeypatch: pytest.MonkeyPatch,
    read_history: Callable[..., object],
    extra_arguments: dict[str, object],
) -> None:
    monkeypatch.setattr(
        service_module, "SqlAlchemyChatExchangeRepository", FailingReadRepository
    )

    _assert_read_failure(
        lambda: read_history(user_id=user_id, db=db, **extra_arguments)
    )
