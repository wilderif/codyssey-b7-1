"""Admin logs HTTP route의 인증과 rendering 계약을 검증한다."""

from __future__ import annotations

import re
from collections.abc import Generator
from dataclasses import replace
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
from app.core.request_id import RequestIdMiddleware


@pytest.fixture
def app(db: Session) -> Generator[FastAPI, None, None]:
    from app.admin.router import router

    application = FastAPI()
    application.state.session = {}
    application.add_middleware(RequestIdMiddleware)

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
        'datetime="2026-08-09T10:30:00+00:00"',
        "2026-08-09 10:30:00 UTC",
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


def test_admin_logs_renders_semantic_table_contract(
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
        lambda *, db: [_metadata_item()],
    )

    response = client.get("/admin/logs")

    assert response.status_code == 200
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in (
        response.text
    )
    assert 'class="admin-table-container"' in response.text
    assert 'role="region"' in response.text
    assert 'aria-labelledby="admin-table-caption"' in response.text
    assert 'tabindex="0"' in response.text
    assert '<caption id="admin-table-caption">Chat 요청별 운영 metadata</caption>' in (
        response.text
    )
    for field_name in (
        "user_id",
        "username",
        "chat_exchange_id",
        "created_at",
        "request_id",
        "user_agent",
        "response_time_ms",
        "status",
        "error_code",
    ):
        assert f'<th scope="col">{field_name}</th>' in response.text
    assert response.text.count('scope="col"') == 9


def test_admin_logs_renders_shared_layout_and_navigation(
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
        lambda *, db: [],
    )

    response = client.get("/admin/logs")

    assert response.status_code == 200
    assert '<link rel="stylesheet" href="/static/styles.css">' in response.text
    assert '<a class="skip-link" href="#main-content">' in response.text
    assert '<a class="admin-nav__link" href="/chat">' in response.text
    assert '<form class="admin-nav__logout" method="post" action="/logout">' in (
        response.text
    )


def test_admin_logs_renders_nullable_metadata_with_placeholder(
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
    item = replace(
        _metadata_item(username=None, user_agent=None),
        status="success",
        error_code=None,
    )
    monkeypatch.setattr(
        router_module,
        "list_admin_chat_operation_metadata",
        lambda *, db: [item],
    )

    response = client.get("/admin/logs")

    assert response.status_code == 200
    assert len(re.findall(r"<td\b[^>]*>\s*-\s*</td>", response.text)) == 3


def test_admin_logs_renders_empty_state_without_table(
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
        lambda *, db: [],
    )

    response = client.get("/admin/logs")

    assert response.status_code == 200
    assert "표시할 운영 기록이 없습니다." in response.text
    assert 'class="admin-empty-state"' in response.text
    assert "<table" not in response.text


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


def test_admin_logs_returns_safe_html_error_for_admin_read_error(
    app: FastAPI,
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """원본 DB 오류가 admin HTML route 경계를 넘어가지 않는다."""

    from app.admin import router as router_module
    from app.admin.errors import AdminReadError

    admin = create_user(
        db=db,
        username="admin-user",
        password_hash="test-hash",
        role=ADMIN_ROLE,
    )
    _log_in(app, admin.id)
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
        response = client.get("/admin/logs")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("text/html")
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
