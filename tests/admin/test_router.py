"""Admin logs HTTP route의 인증과 rendering 계약을 검증한다."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.admin.router as router_module
from app.admin.errors import AdminReadError
from app.admin.schemas import AdminChatOperationMetadataItem
from app.auth.models import ADMIN_ROLE
from app.auth.repository import create_user
from app.chat.models import ChatExchange
from app.core.database import get_db
from app.core.request_id import RequestIdMiddleware


@pytest.fixture
def app(db: Session) -> Generator[FastAPI, None, None]:
    application = FastAPI()
    application.state.session = {}
    application.add_middleware(RequestIdMiddleware)

    @application.middleware("http")
    async def add_session(request: Any, call_next: Any) -> Response:
        request.scope["session"] = dict(application.state.session)
        return await call_next(request)

    application.include_router(router_module.router)
    application.dependency_overrides[get_db] = lambda: db
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def admin_client(app: FastAPI, client: TestClient, db: Session) -> TestClient:
    admin = create_user(
        db=db,
        username="admin-user",
        password_hash="test-hash",
        role=ADMIN_ROLE,
    )
    app.state.session = {"user_id": admin.id}
    return client


def test_admin_logs_redirects_unauthenticated_request_to_login(
    client: TestClient,
) -> None:
    response = client.get("/admin/logs", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_admin_logs_rejects_regular_user(
    app: FastAPI,
    client: TestClient,
    db: Session,
) -> None:
    user = create_user(db=db, username="regular-user", password_hash="test-hash")
    app.state.session = {"user_id": user.id}

    response = client.get("/admin/logs")

    assert response.status_code == 403


def test_admin_logs_renders_safe_metadata_for_admin(
    admin_client: TestClient,
    db: Session,
) -> None:
    user = create_user(
        db=db,
        username='<script>alert("username")</script>',
        password_hash="password-hash-secret",
    )
    exchange = ChatExchange(
        user_id=user.id,
        question="question-secret",
        answer=None,
        status="failed",
        error_message="error-message-secret",
        request_id="request-34",
        user_agent="client<&>",
        response_time_ms=5819,
        error_code="openai_timeout",
    )
    db.add(exchange)
    db.commit()

    response = admin_client.get("/admin/logs")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store"
    for value in (
        str(user.id),
        str(exchange.id),
        "request-34",
        "5,819 ms",
        "failed",
        "openai_timeout",
        "&lt;script&gt;alert(&#34;username&#34;)&lt;/script&gt;",
        "client&lt;&amp;&gt;",
    ):
        assert value in response.text
    for sensitive_value in (
        '<script>alert("username")</script>',
        "question-secret",
        "answer-secret",
        "error-message-secret",
        "password-hash-secret",
    ):
        assert sensitive_value not in response.text


def test_admin_logs_renders_empty_state_without_table(
    admin_client: TestClient,
) -> None:
    response = admin_client.get("/admin/logs")

    assert response.status_code == 200
    assert "표시할 운영 기록이 없습니다." in response.text
    assert 'class="admin-empty-state"' in response.text
    assert "<table" not in response.text


def test_admin_logs_returns_safe_html_error_for_admin_read_error(
    admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """원본 DB 오류가 admin HTML route 경계를 넘어가지 않는다."""

    sensitive_error = (
        "SELECT password_hash FROM users; sqlite secret stack Cookie Authorization"
    )

    def raise_admin_read_error(*, db: Session) -> list[AdminChatOperationMetadataItem]:
        del db
        try:
            raise RuntimeError(sensitive_error)
        except RuntimeError as error:
            raise AdminReadError from error

    monkeypatch.setattr(
        router_module,
        "list_admin_chat_operation_metadata",
        raise_admin_read_error,
    )

    with caplog.at_level("ERROR", logger=router_module.__name__):
        response = admin_client.get("/admin/logs")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store"
    assert response.text == "서버 오류가 발생했습니다."
    assert sensitive_error not in response.text

    request_id = response.headers["x-request-id"]
    assert [record.getMessage() for record in caplog.records] == [
        f"admin_read_failed request_id={request_id}"
    ]
    assert all(record.exc_info is None for record in caplog.records)
    assert sensitive_error not in caplog.text
    assert "Traceback" not in caplog.text


def test_admin_logs_does_not_expose_a_json_api(client: TestClient) -> None:
    response = client.get("/api/admin/logs")

    assert response.status_code == 404
