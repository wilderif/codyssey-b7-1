"""FastAPI application bootstrap과 session middleware 계약을 검증한다."""

from __future__ import annotations

import importlib
import logging
import sys
from collections.abc import Generator
from types import ModuleType
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user_id
from app.core import config as config_module
from app.core.config import Settings
from app.core.database import Base


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

    def record_init_db() -> None:
        initialized_tables.append(set(Base.metadata.tables))

    monkeypatch.setattr(main_module, "init_db", record_init_db)
    application = main_module.create_app(_settings())

    with TestClient(application) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(initialized_tables) == 1
    assert {"users", "chat_exchanges"} <= initialized_tables[0]


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
