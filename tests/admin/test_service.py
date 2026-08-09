"""Admin 운영 metadata Service의 projection과 오류 경계를 검증한다."""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

import app.admin.service as service_module
from app.admin.errors import AdminReadError
from app.admin.repository import AdminChatOperationMetadataRow
from app.admin.schemas import AdminChatOperationMetadataItem


class StaticAdminRepository:
    """Service mapping만 검증하기 위해 고정 row를 반환한다."""

    def __init__(self, *, db: Session) -> None:
        self._db = db

    def list_chat_operation_metadata(self) -> list[AdminChatOperationMetadataRow]:
        return [
            AdminChatOperationMetadataRow(
                user_id=7,
                username=None,
                chat_exchange_id=11,
                created_at=datetime(2026, 8, 8, tzinfo=UTC),
                request_id="request-11",
                user_agent=None,
                response_time_ms=24,
                status="failed",
                error_code="openai_timeout",
            )
        ]


class FailingAdminRepository:
    """Service의 read failure rollback 경계를 재현한다."""

    def __init__(self, *, db: Session) -> None:
        self._db = db

    def list_chat_operation_metadata(self) -> list[AdminChatOperationMetadataRow]:
        raise RuntimeError("admin metadata read failed")


def test_list_metadata_maps_exact_safe_item_and_keeps_missing_username(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service_module,
        "SqlAlchemyAdminRepository",
        StaticAdminRepository,
    )

    items = service_module.list_admin_chat_operation_metadata(db=db)

    assert items == [
        AdminChatOperationMetadataItem(
            user_id=7,
            username=None,
            chat_exchange_id=11,
            created_at=datetime(2026, 8, 8, tzinfo=UTC),
            request_id="request-11",
            user_agent=None,
            response_time_ms=24,
            status="failed",
            error_code="openai_timeout",
        )
    ]
    assert tuple(field.name for field in fields(AdminChatOperationMetadataItem)) == (
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
    assert all(
        not hasattr(items[0], field)
        for field in ("question", "answer", "error_message", "password_hash", "role")
    )


def test_list_metadata_rolls_back_and_raises_read_error_on_query_failure(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service_module,
        "SqlAlchemyAdminRepository",
        FailingAdminRepository,
    )
    db.execute(text("SELECT 1"))
    assert db.in_transaction()

    with pytest.raises(AdminReadError) as captured:
        service_module.list_admin_chat_operation_metadata(db=db)

    assert isinstance(captured.value.__cause__, RuntimeError)
    assert not db.in_transaction()
