"""Server-rendered 인증 route의 HTTP 계약을 검증한다."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.models import ADMIN_ROLE, USER_ROLE
from app.auth.repository import create_user
from app.auth.service import RegistrationError, RegistrationReason
from app.chat.service import ChatExchangeHistoryItem
from app.core.database import get_db


@pytest.fixture
def app(db: Session) -> Generator[FastAPI, None, None]:
    from app.ui.router import router

    application = FastAPI()
    application.state.session = {}

    @application.middleware("http")
    async def add_session(request: Any, call_next: Any) -> Response:
        request.scope["session"] = application.state.session
        return await call_next(request)

    application.include_router(router)
    application.dependency_overrides[get_db] = lambda: db
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _set_session(app: FastAPI, session: dict[str, object]) -> None:
    app.state.session = session


def test_root_redirects_authenticated_user_to_chat(
    app: FastAPI,
    client: TestClient,
    db: Session,
) -> None:
    user = create_user(db=db, username="root-user", password_hash="test-hash")
    db.commit()
    _set_session(app, {"user_id": user.id})

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/chat"


@pytest.mark.parametrize("session", [{}, {"user_id": 999, "stale": "value"}])
def test_root_redirects_invalid_session_to_login_and_clears_it(
    app: FastAPI,
    client: TestClient,
    session: dict[str, object],
) -> None:
    _set_session(app, session)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert app.state.session == {}


@pytest.mark.parametrize(
    ("path", "template_name"),
    [("/signup", "signup.html"), ("/login", "login.html")],
)
def test_get_auth_form_passes_empty_context(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    template_name: str,
) -> None:
    from app.ui import router as router_module

    captured: dict[str, object] = {}

    class CapturingTemplates:
        def TemplateResponse(
            self,
            request: object,
            name: str,
            context: dict[str, object],
            status_code: int = 200,
        ) -> Response:
            captured.update(
                request=request,
                name=name,
                context=context,
                status_code=status_code,
            )
            return HTMLResponse("rendered", status_code=status_code)

    monkeypatch.setattr(router_module, "templates", CapturingTemplates())

    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert captured["request"] is not None
    assert captured["name"] == template_name
    assert captured["context"] == {"error": None, "username": ""}
    assert captured["status_code"] == 200


def test_signup_normalizes_username_without_changing_password(
    app: FastAPI,
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ui import router as router_module

    _set_session(app, {})
    received: dict[str, object] = {}
    raw_password = "  secret-password  "

    def fake_register_user(**kwargs: object) -> None:
        received.update(kwargs)

    monkeypatch.setattr(router_module, "register_user", fake_register_user)

    response = client.post(
        "/signup",
        data={"username": "  new-user  ", "password": raw_password},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert received == {
        "db": db,
        "username": "new-user",
        "password": raw_password,
    }
    assert app.state.session == {}


def test_signup_maps_duplicate_error_to_safe_template_context(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ui import router as router_module

    captured_context: dict[str, object] = {}
    raw_password = "password-must-not-enter-context"

    def reject_registration(**_kwargs: object) -> None:
        raise RegistrationError(RegistrationReason.DUPLICATE_USERNAME)

    class CapturingTemplates:
        def TemplateResponse(
            self,
            request: object,
            name: str,
            context: dict[str, object],
            status_code: int = 200,
        ) -> Response:
            assert request is not None
            assert name == "signup.html"
            captured_context.update(context)
            return HTMLResponse("rendered", status_code=status_code)

    monkeypatch.setattr(router_module, "register_user", reject_registration)
    monkeypatch.setattr(router_module, "templates", CapturingTemplates())

    response = client.post(
        "/signup",
        data={"username": "  escaped-user  ", "password": raw_password},
    )

    assert response.status_code == 400
    assert captured_context == {
        "error": "이미 사용 중인 아이디입니다.",
        "username": "escaped-user",
    }
    assert raw_password not in captured_context.values()


@pytest.mark.parametrize(
    ("username_length", "expected_status"),
    [(2, 400), (3, 303), (30, 303), (31, 400)],
)
def test_signup_enforces_username_length_boundaries(
    client: TestClient,
    username_length: int,
    expected_status: int,
) -> None:
    response = client.post(
        "/signup",
        data={"username": "u" * username_length, "password": "password"},
        follow_redirects=False,
    )

    assert response.status_code == expected_status
    if expected_status == 303:
        assert response.headers["location"] == "/login"
    else:
        assert "아이디는 3자 이상 30자 이하로 입력해주세요." in response.text


@pytest.mark.parametrize(
    ("password_length", "expected_status"),
    [(7, 400), (8, 303), (72, 303), (73, 400)],
)
def test_signup_enforces_password_length_boundaries(
    client: TestClient,
    password_length: int,
    expected_status: int,
) -> None:
    response = client.post(
        "/signup",
        data={"username": "boundary-user", "password": "p" * password_length},
        follow_redirects=False,
    )

    assert response.status_code == expected_status
    if expected_status == 303:
        assert response.headers["location"] == "/login"
    else:
        assert "비밀번호는 8자 이상 72자 이하로 입력해주세요." in response.text


def test_login_sets_session_and_preserves_password_whitespace(
    app: FastAPI,
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ui import router as router_module

    received: dict[str, object] = {}
    raw_password = "  correct-password  "

    def fake_authenticate_user(**kwargs: object) -> object:
        received.update(kwargs)
        return SimpleNamespace(id=42)

    monkeypatch.setattr(router_module, "authenticate_user", fake_authenticate_user)
    _set_session(app, {"stale": "value", "user_id": 1})

    response = client.post(
        "/login",
        data={"username": "  login-user  ", "password": raw_password},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/chat"
    assert received == {
        "db": db,
        "username": "login-user",
        "password": raw_password,
    }
    assert app.state.session == {"user_id": 42}


def test_login_failure_uses_one_safe_message_and_excludes_password_from_context(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ui import router as router_module

    captured_context: dict[str, object] = {}
    raw_password = "password-must-not-enter-context"

    class CapturingTemplates:
        def TemplateResponse(
            self,
            request: object,
            name: str,
            context: dict[str, object],
            status_code: int = 200,
        ) -> Response:
            assert request is not None
            assert name == "login.html"
            captured_context.update(context)
            return HTMLResponse("rendered", status_code=status_code)

    monkeypatch.setattr(router_module, "authenticate_user", lambda **_kwargs: None)
    monkeypatch.setattr(router_module, "templates", CapturingTemplates())

    response = client.post(
        "/login",
        data={"username": "  unknown-user  ", "password": raw_password},
    )

    assert response.status_code == 400
    assert captured_context == {
        "error": "아이디 또는 비밀번호가 올바르지 않습니다.",
        "username": "unknown-user",
    }
    assert raw_password not in captured_context.values()


@pytest.mark.parametrize(
    ("path", "data", "expected_message"),
    [
        (
            "/signup",
            {},
            "아이디는 3자 이상 30자 이하로 입력해주세요.",
        ),
        (
            "/login",
            {},
            "아이디 또는 비밀번호가 올바르지 않습니다.",
        ),
    ],
)
def test_missing_form_fields_return_html_input_error_instead_of_json_422(
    client: TestClient,
    path: str,
    data: dict[str, str],
    expected_message: str,
) -> None:
    response = client.post(path, data=data)

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("text/html")
    assert expected_message in response.text
    assert response.text.lstrip().startswith("<!doctype html>")


@pytest.mark.parametrize("session", [{}, {"user_id": 42, "stale": "value"}])
def test_logout_clears_any_session_and_redirects_to_login(
    app: FastAPI,
    client: TestClient,
    session: dict[str, object],
) -> None:
    _set_session(app, session)

    response = client.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert app.state.session == {}


def test_logout_is_not_available_with_get(client: TestClient) -> None:
    response = client.get("/logout")

    assert response.status_code == 405


def test_chat_passes_service_history_in_latest_first_order_and_exact_context(
    app: FastAPI,
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ui import router as router_module

    user = create_user(db=db, username="chat-user", password_hash="test-hash")
    db.commit()
    _set_session(app, {"user_id": user.id})
    history = [
        ChatExchangeHistoryItem(
            chat_exchange_id=2,
            question="latest-question",
            answer="latest-answer",
            status="success",
            created_at=datetime(2026, 8, 11, 2, tzinfo=UTC),
        ),
        ChatExchangeHistoryItem(
            chat_exchange_id=1,
            question="older-question",
            answer="older-answer",
            status="success",
            created_at=datetime(2026, 8, 11, 1, tzinfo=UTC),
        ),
    ]
    received: dict[str, object] = {}
    captured_context: dict[str, object] = {}

    def fake_list_chat_exchange_history(**kwargs: object) -> object:
        received.update(kwargs)
        return history

    class CapturingTemplates:
        def TemplateResponse(
            self,
            request: object,
            name: str,
            context: dict[str, object],
        ) -> Response:
            assert request is not None
            assert name == "chat.html"
            captured_context.update(context)
            return HTMLResponse("rendered")

    monkeypatch.setattr(
        router_module,
        "list_chat_exchange_history",
        fake_list_chat_exchange_history,
    )
    monkeypatch.setattr(router_module, "templates", CapturingTemplates())

    response = client.get("/chat")

    assert response.status_code == 200
    assert received == {"user_id": user.id, "db": db}
    assert captured_context == {
        "chat_exchanges": history,
        "is_admin": False,
    }
    assert captured_context["chat_exchanges"] is history


@pytest.mark.parametrize(
    ("role", "expected_admin_navigation"),
    [(USER_ROLE, False), (ADMIN_ROLE, True)],
)
def test_chat_renders_admin_navigation_only_for_admin(
    app: FastAPI,
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    expected_admin_navigation: bool,
) -> None:
    from app.ui import router as router_module

    user = create_user(
        db=db,
        username=f"{role}-chat-user",
        password_hash="test-hash",
        role=role,
    )
    db.commit()
    _set_session(app, {"user_id": user.id})
    monkeypatch.setattr(
        router_module,
        "list_chat_exchange_history",
        lambda **_kwargs: [],
    )

    response = client.get("/chat")

    assert response.status_code == 200
    assert ('href="/admin/logs"' in response.text) is expected_admin_navigation
    assert 'method="post" action="/logout"' in response.text


@pytest.mark.parametrize(
    "session",
    [{}, {"user_id": "1"}, {"user_id": 999, "stale": "value"}],
)
def test_chat_clears_invalid_session_without_reading_history(
    app: FastAPI,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session: dict[str, object],
) -> None:
    from app.ui import router as router_module

    def fail_if_called(**_kwargs: object) -> object:
        raise AssertionError("history must not be read without an authenticated user")

    monkeypatch.setattr(
        router_module,
        "list_chat_exchange_history",
        fail_if_called,
    )
    _set_session(app, session)

    response = client.get("/chat", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert app.state.session == {}


def test_chat_allows_history_failure_to_reach_global_exception_handling(
    app: FastAPI,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ui import router as router_module

    user = create_user(
        db=db,
        username="failing-chat-user",
        password_hash="test-hash",
    )
    db.commit()
    _set_session(app, {"user_id": user.id})

    def raise_history_failure(**_kwargs: object) -> object:
        raise RuntimeError("history read failed")

    monkeypatch.setattr(
        router_module,
        "list_chat_exchange_history",
        raise_history_failure,
    )

    with (
        TestClient(app) as raising_client,
        pytest.raises(RuntimeError, match="history read failed"),
    ):
        raising_client.get("/chat")
