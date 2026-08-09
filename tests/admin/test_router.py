"""Admin logs HTTP route의 인증과 rendering 계약을 검증한다."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.admin.schemas import AdminChatOperationMetadataItem
from app.auth.models import ADMIN_ROLE
from app.auth.repository import create_user
from app.core.database import get_db


@pytest.fixture
def app(db: Session) -> Generator[FastAPI, None, None]:
    from app.admin.router import router

    application = FastAPI()
    application.state.session = {}

    @application.middleware("http")
    async def add_session(request: Any, call_next: Any) -> Response:
        request.scope["session"] = dict(application.state.session)
        return await call_next(request)

    application.include_router(router)
    application.dependency_overrides[get_db] = lambda: db
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _log_in(app: FastAPI, user_id: int) -> None:
    app.state.session = {"user_id": user_id}


def _metadata_item(
    *,
    username: str | None = "admin-user",
    user_agent: str | None = "test-client/1.0",
) -> AdminChatOperationMetadataItem:
    return AdminChatOperationMetadataItem(
        user_id=12,
        username=username,
        chat_exchange_id=34,
        created_at=datetime(2026, 8, 9, 10, 30, tzinfo=UTC),
        request_id="request-34",
        user_agent=user_agent,
        response_time_ms=56,
        status="failed",
        error_code="openai_timeout",
    )


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
    _log_in(app, user.id)

    response = client.get("/admin/logs")

    assert response.status_code == 403


def test_admin_logs_renders_safe_metadata_for_admin(
    app: FastAPI,
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.admin import router as router_module

    admin = create_user(
        db=db,
        username="admin-user",
        password_hash="test-hash",
        role=ADMIN_ROLE,
    )
    _log_in(app, admin.id)
    item = _metadata_item(
        username='<script>alert("username")</script>',
        user_agent="client<&>",
    )
    monkeypatch.setattr(
        router_module,
        "list_admin_chat_operation_metadata",
        lambda *, db: [item],
    )

    response = client.get("/admin/logs")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    for value in (
        "12",
        "34",
        "2026-08-09 10:30:00+00:00",
        "request-34",
        "56",
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


def test_admin_logs_renders_orphan_record_with_empty_username(
    app: FastAPI,
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.admin import router as router_module

    admin = create_user(
        db=db,
        username="admin-user",
        password_hash="test-hash",
        role=ADMIN_ROLE,
    )
    _log_in(app, admin.id)
    monkeypatch.setattr(
        router_module,
        "list_admin_chat_operation_metadata",
        lambda *, db: [_metadata_item(username=None, user_agent=None)],
    )

    response = client.get("/admin/logs")

    assert response.status_code == 200
    assert "request-34" in response.text


def test_admin_logs_passes_only_metadata_to_template_context(
    app: FastAPI,
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.admin import router as router_module

    admin = create_user(
        db=db,
        username="admin-user",
        password_hash="test-hash",
        role=ADMIN_ROLE,
    )
    _log_in(app, admin.id)
    item = _metadata_item()
    monkeypatch.setattr(
        router_module,
        "list_admin_chat_operation_metadata",
        lambda *, db: [item],
    )
    captured_context: dict[str, object] = {}

    class CapturingTemplates:
        def TemplateResponse(
            self,
            request: object,
            name: str,
            context: dict[str, object],
        ) -> Response:
            assert request is not None
            assert name == "admin_logs.html"
            captured_context.update(context)
            return Response("rendered", media_type="text/html")

    monkeypatch.setattr(router_module, "templates", CapturingTemplates())

    response = client.get("/admin/logs")

    assert response.status_code == 200
    assert captured_context == {"items": [item]}
    assert all(
        field not in captured_context
        for field in ("question", "answer", "error_message", "password_hash")
    )


def test_admin_logs_does_not_expose_a_json_api(client: TestClient) -> None:
    response = client.get("/api/admin/logs")

    assert response.status_code == 404
