"""ChatExchange Repository의 저장·조회 계약을 검증한다."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.auth.models import User
from app.chat.models import ChatExchange
from app.chat.repository import (
    create_failed_exchange,
    create_success_exchange,
    get_recent_success_exchanges,
    list_user_exchanges,
)


def add_user(db: Session, username: str) -> int:
    user = User(username=username, password_hash="test-hash")
    db.add(user)
    db.flush()
    return user.id


def test_create_exchange_functions_flush_expected_states(
    db: Session,
    user_id: int,
) -> None:
    success = create_success_exchange(
        db=db,
        user_id=user_id,
        question="success question",
        answer="success answer",
    )
    failed = create_failed_exchange(
        db=db,
        user_id=user_id,
        question="failed question",
        error_message="openai_timeout",
    )

    assert success.id > 0
    assert (success.status, success.answer, success.error_message) == (
        "success",
        "success answer",
        None,
    )
    assert failed.id > success.id
    assert (failed.status, failed.answer, failed.error_message) == (
        "failed",
        None,
        "openai_timeout",
    )
    assert db.in_transaction()


def test_recent_success_query_filters_user_status_and_limit(
    db: Session,
    user_id: int,
) -> None:
    other_user_id = add_user(db, "other-user")
    base_time = datetime(2026, 8, 6, tzinfo=UTC)
    for index in range(6):
        db.add(
            ChatExchange(
                user_id=user_id,
                question=f"question-{index}",
                answer=f"answer-{index}",
                status="success",
                error_message=None,
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
                created_at=base_time + timedelta(hours=1),
            ),
            ChatExchange(
                user_id=other_user_id,
                question="other-latest",
                answer="other-answer",
                status="success",
                error_message=None,
                created_at=base_time + timedelta(hours=2),
            ),
        ]
    )
    db.commit()

    exchanges = get_recent_success_exchanges(db=db, user_id=user_id)

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
    same_time = datetime(2026, 8, 6, tzinfo=UTC)
    db.add_all(
        [
            ChatExchange(
                user_id=user_id,
                question="first",
                answer="first answer",
                status="success",
                error_message=None,
                created_at=same_time,
            ),
            ChatExchange(
                user_id=user_id,
                question="second",
                answer="second answer",
                status="success",
                error_message=None,
                created_at=same_time,
            ),
        ]
    )
    db.commit()

    exchanges = get_recent_success_exchanges(db=db, user_id=user_id)

    assert [exchange.question for exchange in exchanges] == ["second", "first"]


@pytest.mark.parametrize("limit", [0, 6])
def test_recent_success_query_rejects_limit_outside_context_contract(
    db: Session,
    user_id: int,
    limit: int,
) -> None:
    with pytest.raises(ValueError, match="between 1 and 5"):
        get_recent_success_exchanges(db=db, user_id=user_id, limit=limit)


def test_list_user_exchanges_returns_only_user_history_newest_first(
    db: Session,
    user_id: int,
) -> None:
    other_user_id = add_user(db, "history-other-user")
    base_time = datetime(2026, 8, 6, tzinfo=UTC)
    db.add_all(
        [
            ChatExchange(
                user_id=user_id,
                question="old",
                answer="old answer",
                status="success",
                error_message=None,
                created_at=base_time,
            ),
            ChatExchange(
                user_id=user_id,
                question="new failed",
                answer=None,
                status="failed",
                error_message="openai_api_error",
                created_at=base_time + timedelta(minutes=1),
            ),
            ChatExchange(
                user_id=other_user_id,
                question="other",
                answer="other answer",
                status="success",
                error_message=None,
                created_at=base_time + timedelta(minutes=2),
            ),
        ]
    )
    db.commit()

    exchanges = list_user_exchanges(db=db, user_id=user_id)

    assert [exchange.question for exchange in exchanges] == ["new failed", "old"]
