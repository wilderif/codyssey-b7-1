"""Admin 운영 metadata read repository의 계약을 검증한다."""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.admin.repository import (
    AdminChatOperationMetadataRow,
    SqlAlchemyAdminRepository,
)
from app.auth.models import User
from app.chat.models import ChatExchange


def add_user(db: Session, username: str) -> int:
    user = User(username=username, password_hash="test-hash")
    db.add(user)
    db.flush()
    return user.id


def add_exchange(
    db: Session,
    *,
    user_id: int,
    request_id: str,
    created_at: datetime,
    status: str = "success",
) -> ChatExchange:
    failed = status == "failed"
    exchange = ChatExchange(
        user_id=user_id,
        question="private question",
        answer=None if failed else "private answer",
        status=status,
        error_message="private error" if failed else None,
        request_id=request_id,
        user_agent="test-agent/1.0",
        response_time_ms=12,
        error_code="openai_timeout" if failed else None,
        created_at=created_at,
    )
    db.add(exchange)
    db.flush()
    return exchange


def test_list_metadata_returns_exact_safe_projection_newest_first_and_keeps_orphan(
    db: Session,
) -> None:
    first_user_id = add_user(db, "first-user")
    second_user_id = add_user(db, "second-user")
    orphan_user_id = add_user(db, "removed-user")
    base_time = datetime(2026, 8, 8, tzinfo=UTC)
    old_exchange = add_exchange(
        db,
        user_id=first_user_id,
        request_id="old-request",
        created_at=base_time,
    )
    tie_first_exchange = add_exchange(
        db,
        user_id=first_user_id,
        request_id="tie-first-request",
        created_at=base_time + timedelta(minutes=1),
    )
    tie_second_exchange = add_exchange(
        db,
        user_id=second_user_id,
        request_id="tie-second-request",
        created_at=base_time + timedelta(minutes=1),
        status="failed",
    )
    orphan_exchange = add_exchange(
        db,
        user_id=orphan_user_id,
        request_id="orphan-request",
        created_at=base_time + timedelta(minutes=2),
    )
    expected_exchange_ids = [
        orphan_exchange.id,
        tie_second_exchange.id,
        tie_first_exchange.id,
        old_exchange.id,
    ]
    db.commit()

    engine = db.get_bind()
    assert isinstance(engine, Engine)
    db.close()
    raw_connection = engine.raw_connection()
    try:
        raw_connection.execute("PRAGMA foreign_keys = OFF")
        raw_connection.execute(
            "DELETE FROM users WHERE id = ?",
            (orphan_user_id,),
        )
        raw_connection.commit()
        raw_connection.execute("PRAGMA foreign_keys = ON")
    finally:
        raw_connection.close()

    with Session(engine) as query_db:
        rows = SqlAlchemyAdminRepository(db=query_db).list_chat_operation_metadata()

    assert [row.chat_exchange_id for row in rows] == expected_exchange_ids
    assert [(row.user_id, row.username) for row in rows] == [
        (orphan_user_id, None),
        (second_user_id, "second-user"),
        (first_user_id, "first-user"),
        (first_user_id, "first-user"),
    ]
    assert tuple(field.name for field in fields(AdminChatOperationMetadataRow)) == (
        "user_id",
        "username",
        "chat_exchange_id",
        "created_at",
        "request_id",
        "user_agent",
        "response_time_ms",
        "status",
        "error_code",
    )
    assert set(asdict(rows[0])) == {
        "user_id",
        "username",
        "chat_exchange_id",
        "created_at",
        "request_id",
        "user_agent",
        "response_time_ms",
        "status",
        "error_code",
    }
    assert all(
        not hasattr(rows[0], field)
        for field in ("question", "answer", "error_message", "password_hash", "role")
    )


def test_list_metadata_never_commits(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = add_user(db, "read-only-user")
    add_exchange(
        db,
        user_id=user_id,
        request_id="read-only-request",
        created_at=datetime(2026, 8, 8, tzinfo=UTC),
    )
    db.commit()

    def fail_if_commit_called() -> None:
        raise AssertionError("read repository must not commit")

    monkeypatch.setattr(db, "commit", fail_if_commit_called)

    rows = SqlAlchemyAdminRepository(db=db).list_chat_operation_metadata()

    assert [row.request_id for row in rows] == ["read-only-request"]
