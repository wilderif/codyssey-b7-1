"""ChatExchange Repository의 저장·조회 계약을 검증한다."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.chat.models import ChatExchange
from app.chat.repository import SqlAlchemyChatExchangeRepository


def test_repository_create_exchange_methods_flush_expected_states(
    db: Session,
    user_id: int,
) -> None:
    repository = SqlAlchemyChatExchangeRepository(db=db)

    success = repository.create_success_exchange(
        user_id=user_id,
        question="success question",
        answer="success answer",
        request_id="request-success",
        user_agent="test-agent/1.0",
        response_time_ms=12,
    )
    failed = repository.create_failed_exchange(
        user_id=user_id,
        question="failed question",
        error_message="openai_timeout",
        request_id="request-failed",
        user_agent=None,
        response_time_ms=34,
        error_code="openai_timeout",
    )

    assert success.id > 0
    assert (
        success.status,
        success.answer,
        success.error_message,
        success.request_id,
        success.user_agent,
        success.response_time_ms,
        success.error_code,
    ) == (
        "success",
        "success answer",
        None,
        "request-success",
        "test-agent/1.0",
        12,
        None,
    )
    assert failed.id > success.id
    assert (
        failed.status,
        failed.answer,
        failed.error_message,
        failed.request_id,
        failed.user_agent,
        failed.response_time_ms,
        failed.error_code,
    ) == (
        "failed",
        None,
        "openai_timeout",
        "request-failed",
        None,
        34,
        "openai_timeout",
    )
    assert db.in_transaction()


def test_chat_exchange_schema_enforces_operational_metadata_contract(
    db: Session,
    user_id: int,
) -> None:
    repository = SqlAlchemyChatExchangeRepository(db=db)

    repository.create_success_exchange(
        user_id=user_id,
        question="first question",
        answer="first answer",
        request_id="duplicate-request-id",
        user_agent="a" * 512,
        response_time_ms=0,
    )
    db.commit()

    invalid_exchanges = [
        ChatExchange(
            user_id=user_id,
            question="duplicate request",
            answer="answer",
            status="success",
            error_message=None,
            request_id="duplicate-request-id",
            user_agent=None,
            response_time_ms=1,
            error_code=None,
        ),
        ChatExchange(
            user_id=user_id,
            question="long agent",
            answer="answer",
            status="success",
            error_message=None,
            request_id="long-agent-request",
            user_agent="a" * 513,
            response_time_ms=1,
            error_code=None,
        ),
        ChatExchange(
            user_id=user_id,
            question="negative duration",
            answer="answer",
            status="success",
            error_message=None,
            request_id="negative-duration-request",
            user_agent=None,
            response_time_ms=-1,
            error_code=None,
        ),
        ChatExchange(
            user_id=user_id,
            question="success error code",
            answer="answer",
            status="success",
            error_message=None,
            request_id="success-error-code-request",
            user_agent=None,
            response_time_ms=1,
            error_code="openai_api_error",
        ),
        ChatExchange(
            user_id=user_id,
            question="failed without error code",
            answer=None,
            status="failed",
            error_message="openai_api_error",
            request_id="failed-without-code-request",
            user_agent=None,
            response_time_ms=1,
            error_code=None,
        ),
        ChatExchange(
            user_id=user_id,
            question="long error code",
            answer=None,
            status="failed",
            error_message="openai_api_error",
            request_id="long-error-code-request",
            user_agent=None,
            response_time_ms=1,
            error_code="e" * 51,
        ),
        ChatExchange(
            user_id=user_id,
            question="long request id",
            answer="answer",
            status="success",
            error_message=None,
            request_id="r" * 65,
            user_agent=None,
            response_time_ms=1,
            error_code=None,
        ),
    ]

    for exchange in invalid_exchanges:
        db.add(exchange)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


def test_new_sqlite_database_creates_operational_metadata_schema() -> None:
    engine = create_engine("sqlite://")
    try:
        ChatExchange.metadata.create_all(engine)
        columns = {
            column["name"] for column in inspect(engine).get_columns("chat_exchanges")
        }
    finally:
        engine.dispose()

    assert {
        "request_id",
        "user_agent",
        "response_time_ms",
        "error_code",
    } <= columns


def test_recent_success_query_filters_user_status_and_limit(
    db: Session,
    user_id: int,
    user_id_factory: Callable[[str], int],
) -> None:
    repository = SqlAlchemyChatExchangeRepository(db=db)
    other_user_id = user_id_factory("other-user")
    base_time = datetime(2026, 8, 6, tzinfo=UTC)
    for index in range(6):
        db.add(
            ChatExchange(
                user_id=user_id,
                question=f"question-{index}",
                answer=f"answer-{index}",
                status="success",
                error_message=None,
                request_id=f"recent-success-{index}",
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
                question="failed-latest",
                answer=None,
                status="failed",
                error_message="openai_timeout",
                request_id="recent-failed",
                user_agent=None,
                response_time_ms=1,
                error_code="openai_timeout",
                created_at=base_time + timedelta(hours=1),
            ),
            ChatExchange(
                user_id=other_user_id,
                question="other-latest",
                answer="other-answer",
                status="success",
                error_message=None,
                request_id="recent-other",
                user_agent=None,
                response_time_ms=1,
                error_code=None,
                created_at=base_time + timedelta(hours=2),
            ),
        ]
    )
    db.commit()

    exchanges = repository.get_recent_success_exchanges(user_id=user_id)

    assert [exchange.question for exchange in exchanges] == [
        "question-5",
        "question-4",
        "question-3",
        "question-2",
        "question-1",
    ]


def test_recent_success_query_uses_id_as_created_at_tie_breaker(
    db: Session,
    user_id: int,
) -> None:
    repository = SqlAlchemyChatExchangeRepository(db=db)
    same_time = datetime(2026, 8, 6, tzinfo=UTC)
    db.add_all(
        [
            ChatExchange(
                user_id=user_id,
                question="first",
                answer="first answer",
                status="success",
                error_message=None,
                request_id="tie-first",
                user_agent=None,
                response_time_ms=1,
                error_code=None,
                created_at=same_time,
            ),
            ChatExchange(
                user_id=user_id,
                question="second",
                answer="second answer",
                status="success",
                error_message=None,
                request_id="tie-second",
                user_agent=None,
                response_time_ms=1,
                error_code=None,
                created_at=same_time,
            ),
        ]
    )
    db.commit()

    exchanges = repository.get_recent_success_exchanges(user_id=user_id)

    assert [exchange.question for exchange in exchanges] == ["second", "first"]


@pytest.mark.parametrize("limit", [0, 6])
def test_recent_success_query_rejects_limit_outside_context_contract(
    db: Session,
    user_id: int,
    limit: int,
) -> None:
    repository = SqlAlchemyChatExchangeRepository(db=db)

    with pytest.raises(ValueError, match="between 1 and 5"):
        repository.get_recent_success_exchanges(user_id=user_id, limit=limit)


def test_list_user_exchanges_returns_only_user_history_newest_first(
    db: Session,
    user_id: int,
    user_id_factory: Callable[[str], int],
) -> None:
    repository = SqlAlchemyChatExchangeRepository(db=db)
    other_user_id = user_id_factory("history-other-user")
    base_time = datetime(2026, 8, 6, tzinfo=UTC)
    db.add_all(
        [
            ChatExchange(
                user_id=user_id,
                question="old",
                answer="old answer",
                status="success",
                error_message=None,
                request_id="history-old",
                user_agent=None,
                response_time_ms=1,
                error_code=None,
                created_at=base_time,
            ),
            ChatExchange(
                user_id=user_id,
                question="new failed",
                answer=None,
                status="failed",
                error_message="openai_api_error",
                request_id="history-failed",
                user_agent=None,
                response_time_ms=1,
                error_code="openai_api_error",
                created_at=base_time + timedelta(minutes=1),
            ),
            ChatExchange(
                user_id=other_user_id,
                question="other",
                answer="other answer",
                status="success",
                error_message=None,
                request_id="history-other",
                user_agent=None,
                response_time_ms=1,
                error_code=None,
                created_at=base_time + timedelta(minutes=2),
            ),
        ]
    )
    db.commit()

    exchanges = repository.list_user_exchanges(user_id=user_id)

    assert [exchange.question for exchange in exchanges] == ["new failed", "old"]


def test_get_user_exchange_returns_only_the_requesting_users_record(
    db: Session,
    user_id: int,
    user_id_factory: Callable[[str], int],
) -> None:
    repository = SqlAlchemyChatExchangeRepository(db=db)
    other_user_id = user_id_factory("single-history-other-user")
    own_exchange = repository.create_success_exchange(
        user_id=user_id,
        question="mine",
        answer="my answer",
        request_id="single-history-mine",
        user_agent=None,
        response_time_ms=1,
    )
    other_exchange = repository.create_success_exchange(
        user_id=other_user_id,
        question="other",
        answer="other answer",
        request_id="single-history-other",
        user_agent=None,
        response_time_ms=1,
    )
    db.commit()

    own_result = repository.get_user_exchange(
        user_id=user_id,
        chat_exchange_id=own_exchange.id,
    )
    foreign_result = repository.get_user_exchange(
        user_id=user_id,
        chat_exchange_id=other_exchange.id,
    )
    missing_result = repository.get_user_exchange(
        user_id=user_id,
        chat_exchange_id=9999,
    )

    assert own_result is not None
    assert own_result.id == own_exchange.id
    assert foreign_result is None
    assert missing_result is None


def test_chat_exchange_normalizes_persisted_timestamps_to_utc(
    db: Session,
    user_id: int,
) -> None:
    exchange = ChatExchange(
        user_id=user_id,
        question="timezone question",
        answer="timezone answer",
        status="success",
        error_message=None,
        request_id="timezone-request",
        user_agent=None,
        response_time_ms=1,
        error_code=None,
        created_at=datetime(2026, 8, 6, 9, tzinfo=timezone(timedelta(hours=9))),
    )
    db.add(exchange)
    db.commit()
    db.expire_all()

    saved = db.get(ChatExchange, exchange.id)

    assert saved is not None
    assert saved.created_at == datetime(2026, 8, 6, tzinfo=UTC)
    assert saved.created_at.tzinfo == UTC


def test_chat_exchange_rejects_naive_timestamps(
    db: Session,
    user_id: int,
) -> None:
    db.add(
        ChatExchange(
            user_id=user_id,
            question="naive timestamp question",
            answer="naive timestamp answer",
            status="success",
            error_message=None,
            request_id="naive-timestamp-request",
            user_agent=None,
            response_time_ms=1,
            error_code=None,
            created_at=datetime.fromisoformat("2026-08-06T00:00:00"),
        )
    )

    with pytest.raises(StatementError, match="timezone-aware"):
        db.commit()

    db.rollback()
