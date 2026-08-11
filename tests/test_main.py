"""FastAPI application bootstrap과 session middleware 계약을 검증한다."""

from __future__ import annotations

import importlib
import logging
import sys
from collections.abc import Generator
from contextlib import contextmanager, nullcontext
from types import ModuleType
from typing import Annotated
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user_id
from app.core import config as config_module
from app.core.config import Settings
from app.core.database import Base
from app.core.request_id import REQUEST_ID_HEADER


def _settings(
    *,
    app_env: str = "local",
    log_level: str = "INFO",
) -> Settings:
    values: dict[str, object] = {
        "SESSION_SECRET": "test-session-secret",
        "APP_ENV": app_env,
        "LOG_LEVEL": log_level,
    }
    if app_env == "production":
        values.update(
            OPENAI_API_KEY="test-openai-key",
            OPENAI_MODEL="test-openai-model",
        )
    return Settings.model_validate(values)


@pytest.fixture
def main_module(monkeypatch: pytest.MonkeyPatch) -> Generator[ModuleType, None, None]:
    root_logger = logging.getLogger()
    previous_level = root_logger.level
    monkeypatch.setattr(config_module, "settings", _settings())
    sys.modules.pop("app.main", None)
    module = importlib.import_module("app.main")
    monkeypatch.setattr(module, "SessionLocal", lambda: nullcontext(object()))
    monkeypatch.setattr(module, "ensure_initial_admin", lambda **_kwargs: None)
    try:
        yield module
    finally:
        root_logger.setLevel(previous_level)
        sys.modules.pop("app.main", None)


@pytest.mark.parametrize("session_secret", [None, "   "])
def test_main_import_fails_safely_without_session_secret(
    monkeypatch: pytest.MonkeyPatch,
    session_secret: str | None,
) -> None:
    configured = Settings.model_validate(
        {"APP_ENV": "local", "SESSION_SECRET": session_secret}
    )
    monkeypatch.setattr(config_module, "settings", configured)
    sys.modules.pop("app.main", None)

    with pytest.raises(RuntimeError, match="SESSION_SECRET") as captured:
        importlib.import_module("app.main")

    assert "None" not in str(captured.value)
    sys.modules.pop("app.main", None)


def test_health_initializes_registered_models_before_serving_requests(
    main_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialized_tables: list[set[str]] = []
    startup_events: list[str] = []
    db_session = object()
    configured = _settings()

    def record_init_db() -> None:
        startup_events.append("init_db")
        initialized_tables.append(set(Base.metadata.tables))

    @contextmanager
    def session_scope() -> Generator[object, None, None]:
        startup_events.append("session_opened")
        try:
            yield db_session
        finally:
            startup_events.append("session_closed")

    def record_initial_admin(*, db: object, app_settings: Settings) -> None:
        assert db is db_session
        assert app_settings is configured
        startup_events.append("initial_admin_ensured")

    monkeypatch.setattr(main_module, "init_db", record_init_db)
    monkeypatch.setattr(main_module, "SessionLocal", session_scope)
    monkeypatch.setattr(main_module, "ensure_initial_admin", record_initial_admin)
    application = main_module.create_app(configured)

    with TestClient(application) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert UUID(response.headers[REQUEST_ID_HEADER]).version == 4
    assert len(initialized_tables) == 1
    assert {"users", "chat_exchanges"} <= initialized_tables[0]
    assert startup_events == [
        "init_db",
        "session_opened",
        "initial_admin_ensured",
        "session_closed",
    ]


def test_admin_bootstrap_failure_closes_session_and_stops_startup(
    main_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    startup_events: list[str] = []
    db_session = object()
    configured = _settings()

    def record_init_db() -> None:
        startup_events.append("init_db")

    @contextmanager
    def session_scope() -> Generator[object, None, None]:
        startup_events.append("session_opened")
        try:
            yield db_session
        finally:
            startup_events.append("session_closed")

    def fail_initial_admin(*, db: object, app_settings: Settings) -> None:
        assert db is db_session
        assert app_settings is configured
        startup_events.append("initial_admin_failed")
        raise RuntimeError("initial admin bootstrap failed")

    monkeypatch.setattr(main_module, "init_db", record_init_db)
    monkeypatch.setattr(main_module, "SessionLocal", session_scope)
    monkeypatch.setattr(main_module, "ensure_initial_admin", fail_initial_admin)
    application = main_module.create_app(configured)

    with (
        pytest.raises(RuntimeError, match="initial admin bootstrap failed"),
        TestClient(application),
    ):
        pytest.fail("startup failure must prevent request handling")

    assert startup_events == [
        "init_db",
        "session_opened",
        "initial_admin_failed",
        "session_closed",
    ]


@pytest.mark.parametrize(
    ("app_env", "secure_expected"),
    [("local", False), ("production", True)],
)
def test_session_cookie_security_attributes_follow_environment(
    main_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    app_env: str,
    secure_expected: bool,
) -> None:
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    application = main_module.create_app(_settings(app_env=app_env))
    _add_session_test_routes(application)

    with TestClient(application) as client:
        response = client.post("/_test/session")

    cookie_parts = {
        part.strip().lower() for part in response.headers["set-cookie"].split(";")
    }
    assert "httponly" in cookie_parts
    assert "samesite=lax" in cookie_parts
    assert "max-age=28800" in cookie_parts
    assert ("secure" in cookie_parts) is secure_expected


def test_tampered_session_cookie_is_not_used_for_authentication(
    main_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    application = main_module.create_app(_settings())
    _add_session_test_routes(application)

    with TestClient(application) as client:
        session_response = client.post("/_test/session")
        valid_cookie = session_response.cookies["session"]
        client.cookies.clear()
        client.cookies.set("session", valid_cookie + "tampered")

        response = client.get("/api/_test/session-user")

    assert response.status_code == 401
    assert response.json() == {
        "code": "not_authenticated",
        "detail": "로그인이 필요합니다.",
    }


def test_create_app_sets_configured_logging_level(main_module: ModuleType) -> None:
    main_module.create_app(_settings(log_level="WARNING"))

    assert logging.getLogger().level == logging.WARNING


def test_create_app_registers_ui_router_once(main_module: ModuleType) -> None:
    application = main_module.create_app(_settings())

    matching_routes = [
        route
        for route in application.routes
        if getattr(route, "original_router", None) is main_module.ui_router
    ]

    assert len(matching_routes) == 1


def test_create_app_mounts_static_files_once(main_module: ModuleType) -> None:
    application = main_module.create_app(_settings())

    matching_routes = [
        route
        for route in application.routes
        if getattr(route, "path", None) == "/static"
    ]

    assert len(matching_routes) == 1
    assert matching_routes[0].name == "static"


def test_static_assets_are_public_and_have_expected_content_types(
    main_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    application = main_module.create_app(_settings())

    with TestClient(application) as client:
        stylesheet_response = client.get("/static/styles.css")
        script_response = client.get("/static/chat.js")

    assert stylesheet_response.status_code == 200
    assert stylesheet_response.headers["content-type"].startswith("text/css")
    assert UUID(stylesheet_response.headers[REQUEST_ID_HEADER]).version == 4
    assert script_response.status_code == 200
    assert script_response.headers["content-type"].startswith("text/javascript")
    assert UUID(script_response.headers[REQUEST_ID_HEADER]).version == 4


def test_missing_static_asset_returns_404(
    main_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    application = main_module.create_app(_settings())

    with TestClient(application) as client:
        response = client.get("/static/missing.css")

    assert response.status_code == 404
    assert UUID(response.headers[REQUEST_ID_HEADER]).version == 4


def test_unhandled_api_error_preserves_request_id_on_500_response(
    main_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    application = main_module.create_app(_settings())

    @application.get("/api/_test/unhandled-error")
    def raise_unhandled_error() -> None:
        raise RuntimeError("unexpected failure")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/api/_test/unhandled-error")

    assert response.status_code == 500
    assert response.json() == {
        "code": "internal_error",
        "detail": "서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
    }
    assert UUID(response.headers[REQUEST_ID_HEADER]).version == 4


def test_unhandled_html_error_returns_safe_response_with_request_id(
    main_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    application = main_module.create_app(_settings())

    @application.get("/_test/unhandled-html-error")
    def raise_unhandled_html_error() -> None:
        raise RuntimeError("SELECT password_hash FROM users")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/_test/unhandled-html-error")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == "서버 오류가 발생했습니다."
    assert "password_hash" not in response.text
    assert UUID(response.headers[REQUEST_ID_HEADER]).version == 4


def _add_session_test_routes(application: FastAPI) -> None:
    @application.post("/_test/session")
    def set_session(request: Request) -> dict[str, str]:
        request.session["user_id"] = 42
        return {"status": "created"}

    @application.get("/api/_test/session-user")
    def get_session_user(
        user_id: Annotated[int, Depends(get_current_user_id)],
    ) -> dict[str, int]:
        return {"user_id": user_id}
