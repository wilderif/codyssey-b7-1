"""Final application Auth·Chat·Admin 연결 계약 평가다."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Generator
from contextlib import nullcontext
from dataclasses import fields
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace
from typing import Self

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.auth.models import ADMIN_ROLE, User
from app.auth.repository import create_user
from app.chat.models import ChatExchange
from app.core import config as config_module
from app.core.config import Settings
from app.core.database import get_db


@pytest.fixture
def main_module(monkeypatch: pytest.MonkeyPatch) -> Generator[ModuleType, None, None]:
    """환경과 무관하게 application module을 test 설정으로 import한다."""

    monkeypatch.setattr(
        config_module,
        "settings",
        Settings(
            session_secret=SecretStr("evaluation-session-secret"),
            admin_initial_password=SecretStr("evaluation-password"),
        ),
    )
    sys.modules.pop("app.main", None)
    module = importlib.import_module("app.main")
    try:
        yield module
    finally:
        sys.modules.pop("app.main", None)


@pytest.fixture
def app(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    main_module: ModuleType,
) -> Generator[FastAPI, None, None]:
    """create_app의 실제 middleware/router/lifespan을 test DB에 연결한다."""

    monkeypatch.setattr(main_module, "init_db", lambda: None)

    monkeypatch.setattr(main_module, "SessionLocal", lambda: nullcontext(object()))
    monkeypatch.setattr(main_module, "ensure_initial_admin", lambda **_kwargs: None)
    application = main_module.create_app(
        Settings(
            session_secret=SecretStr("evaluation-session-secret"),
            admin_initial_password=SecretStr("evaluation-password"),
        )
    )
    application.dependency_overrides[get_db] = lambda: db
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _seed_users(db: Session) -> tuple[User, User]:
    from app.core.security import hash_password

    password_hash = hash_password("test-password")
    user = create_user(db=db, username="evaluation-user", password_hash=password_hash)
    admin = create_user(
        db=db,
        username="evaluation-admin",
        password_hash=password_hash,
        role=ADMIN_ROLE,
    )
    db.commit()
    return user, admin


def _exchange(
    db: Session,
    *,
    user_id: int,
    question: str,
    answer: str | None,
    status: str,
    request_id: str,
    created_at: datetime,
    error_code: str | None = None,
) -> ChatExchange:
    exchange = ChatExchange(
        user_id=user_id,
        question=question,
        answer=answer,
        status=status,
        error_message=None if status == "success" else "safe failure message",
        error_code=error_code,
        request_id=request_id,
        user_agent="evaluation-agent/1.0",
        response_time_ms=123,
        created_at=created_at,
    )
    db.add(exchange)
    db.flush()
    return exchange


def _login(client: TestClient, username: str) -> None:
    response = client.post(
        "/login",
        data={"username": username, "password": "test-password"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_admin_chat_contract_projection_history_and_visibility(
    app: FastAPI,
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, admin = _seed_users(db)
    assert (user.role, admin.role) == ("user", "admin")
    user_exchange = _exchange(
        db,
        user_id=user.id,
        question="user question secret",
        answer="user answer secret",
        status="success",
        request_id="user-request-id",
        created_at=datetime(2026, 8, 11, 1, tzinfo=UTC),
    )
    failed_exchange = _exchange(
        db,
        user_id=admin.id,
        question="admin failed question secret",
        answer=None,
        status="failed",
        error_code="openai_timeout",
        request_id="admin-failed-request-id",
        created_at=datetime(2026, 8, 11, 2, tzinfo=UTC),
    )
    assert (
        failed_exchange.answer is None
        and failed_exchange.status == "failed"
        and failed_exchange.error_code is not None
    )
    db.commit()

    from app.admin.repository import SqlAlchemyAdminRepository

    rows = SqlAlchemyAdminRepository(db=db).list_chat_operation_metadata()
    row_by_exchange_id = {row.chat_exchange_id: row for row in rows}
    assert set(row_by_exchange_id) == {user_exchange.id, failed_exchange.id}
    assert tuple(field.name for field in fields(rows[0])) == (
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
    failed_row = row_by_exchange_id[failed_exchange.id]
    assert (
        failed_row.user_id,
        failed_row.username,
        failed_row.chat_exchange_id,
        failed_row.created_at,
        failed_row.request_id,
        failed_row.user_agent,
        failed_row.response_time_ms,
        failed_row.status,
        failed_row.error_code,
    ) == (
        admin.id,
        "evaluation-admin",
        failed_exchange.id,
        failed_exchange.created_at,
        "admin-failed-request-id",
        "evaluation-agent/1.0",
        123,
        "failed",
        "openai_timeout",
    )
    success_row = row_by_exchange_id[user_exchange.id]
    assert (
        success_row.user_id,
        success_row.username,
        success_row.chat_exchange_id,
        success_row.created_at,
        success_row.request_id,
        success_row.user_agent,
        success_row.response_time_ms,
        success_row.status,
        success_row.error_code,
    ) == (
        user.id,
        "evaluation-user",
        user_exchange.id,
        user_exchange.created_at,
        "user-request-id",
        "evaluation-agent/1.0",
        123,
        "success",
        None,
    )
    assert not hasattr(failed_row, "question")
    assert not hasattr(failed_row, "answer")

    anonymous_admin = client.get("/admin/logs", follow_redirects=False)
    assert anonymous_admin.status_code == 303
    assert anonymous_admin.headers["location"] == "/login"
    _login(client, "evaluation-user")
    assert client.get("/admin/logs").status_code == 403
    history = client.get("/api/chat-exchanges")
    assert history.status_code == 200
    assert [item["chat_exchange_id"] for item in history.json()] == [user_exchange.id]
    assert (
        not {
            "request_id",
            "user_agent",
            "response_time_ms",
            "error_code",
            "error_message",
        }
        & history.json()[0].keys()
    )
    assert "admin failed question secret" not in history.text
    detail = client.get(f"/api/chat-exchanges/{user_exchange.id}")
    assert detail.status_code == 200
    assert set(detail.json()) == {
        "chat_exchange_id",
        "question",
        "answer",
        "status",
        "created_at",
    }

    _login(client, "evaluation-admin")
    logs = client.get("/admin/logs")
    assert logs.status_code == 200
    assert "admin-failed-request-id" in logs.text
    for secret in (
        "user question secret",
        "user answer secret",
        "admin failed question secret",
    ):
        assert secret not in logs.text

    paths = {path for route in app.routes if (path := getattr(route, "path", None))}
    api_paths = {path for path in paths if path.startswith("/api/")}
    assert api_paths <= {
        "/api/chat",
        "/api/chat-exchanges",
        "/api/chat-exchanges/{chat_exchange_id}",
    }
    assert "/logs" not in paths
    assert set(inspect(db.get_bind()).get_table_names()) == {
        "users",
        "chat_exchanges",
    }


def test_admin_chat_contract_request_id_matches_persisted_exchange(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _user, _admin = _seed_users(db)
    import app.chat.service as chat_service

    class FakeOpenAIClient:
        def __init__(self) -> None:
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=self.create,
                )
            )

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def create(self, **_kwargs: object) -> object:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content="generated answer"))
                ]
            )

    monkeypatch.setattr(chat_service, "create_openai_client", FakeOpenAIClient)
    monkeypatch.setattr(chat_service, "get_openai_model", lambda: "evaluation-model")
    _login(client, "evaluation-user")
    with caplog.at_level("INFO", logger="app.chat.service"):
        response = client.post(
            "/api/chat",
            json={"message": "request scoped question"},
            headers={"user-agent": "evaluation-agent/1.0"},
        )
    assert response.status_code == 200
    assert set(response.json()) == {"chat_exchange_id", "answer", "created_at"}
    request_id = response.headers["x-request-id"]
    saved = db.query(ChatExchange).filter_by(request_id=request_id).one()
    assert saved.answer == "generated answer"
    assert saved.request_id == request_id
    assert saved.status == "success"
    assert saved.user_agent == "evaluation-agent/1.0"
    assert saved.response_time_ms >= 0
    assert saved.error_code is None
    assert saved.error_message is None
    messages = [record.getMessage() for record in caplog.records]
    assert any(
        message.startswith("request_received ") and request_id in message
        for message in messages
    )
    assert any(
        message.startswith("db_save_succeeded ") and request_id in message
        for message in messages
    )
