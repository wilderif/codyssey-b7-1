"""Chat REST router의 사용자별 JSON 계약을 검증한다."""

from __future__ import annotations

import asyncio
from collections.abc import Generator, Sequence
from datetime import UTC, datetime
from unittest.mock import ANY

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user_id
from app.auth.models import User
from app.chat.context import ChatMessage
from app.chat.errors import (
    AppError,
    ChatConfigurationError,
    ChatGenerationError,
    ChatPersistenceError,
    ChatTimeoutError,
    ChatValidationError,
)
from app.chat.models import ChatExchange
from app.chat.repository import SqlAlchemyChatExchangeRepository
from app.chat.service import ChatResult, ChatService
from app.core.database import get_db


@pytest.fixture
def app(db: Session) -> Generator[FastAPI, None, None]:
    from app.chat.router import (
        app_error_handler,
        http_exception_handler,
        router,
        unhandled_exception_handler,
        validation_exception_handler,
    )

    application = FastAPI()

    @application.middleware("http")
    async def add_empty_session(request, call_next):  # type: ignore[no-untyped-def]
        request.scope["session"] = {}
        return await call_next(request)

    application.include_router(router)
    application.add_exception_handler(
        RequestValidationError, validation_exception_handler
    )
    application.add_exception_handler(AppError, app_error_handler)
    application.add_exception_handler(HTTPException, http_exception_handler)
    application.add_exception_handler(Exception, unhandled_exception_handler)
    application.dependency_overrides[get_db] = lambda: db
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _login(app: FastAPI, user_id: int) -> None:
    app.dependency_overrides[get_current_user_id] = lambda: user_id


def _add_exchange(
    db: Session,
    *,
    user_id: int,
    question: str,
    answer: str | None,
    status: str,
    request_id: str,
    error_message: str | None = None,
    error_code: str | None = None,
) -> ChatExchange:
    exchange = ChatExchange(
        user_id=user_id,
        question=question,
        answer=answer,
        status=status,
        error_message=error_message,
        error_code=error_code,
        request_id=request_id,
        user_agent="secret-cookie-agent",
        response_time_ms=1,
        created_at=datetime(2026, 8, 7, tzinfo=UTC),
    )
    db.add(exchange)
    db.commit()
    return exchange


def test_post_chat_returns_contract_and_passes_user_agent(
    app: FastAPI,
    client: TestClient,
    user_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.chat import router as router_module

    _login(app, user_id)
    received: dict[str, object] = {}

    async def fake_process_chat(**kwargs: object) -> ChatResult:
        received.update(kwargs)
        return ChatResult(
            chat_exchange_id=15,
            answer="answer",
            created_at=datetime(2026, 8, 7, tzinfo=UTC),
        )

    monkeypatch.setattr(router_module, "process_chat", fake_process_chat)

    response = client.post(
        "/api/chat",
        json={"message": "question"},
        headers={"user-agent": "router-test/1.0"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "chat_exchange_id": 15,
        "answer": "answer",
        "created_at": "2026-08-07T00:00:00Z",
    }
    assert received == {
        "user_id": user_id,
        "message": "question",
        "user_agent": "router-test/1.0",
        "db": ANY,
    }


@pytest.mark.parametrize(
    ("header_value", "expected_user_agent"),
    [
        ("a" * 512, "a" * 512),
        ("b" * 513, "b" * 512),
    ],
)
def test_post_chat_limits_persisted_user_agent_to_database_boundary(
    app: FastAPI,
    client: TestClient,
    user_id: int,
    monkeypatch: pytest.MonkeyPatch,
    header_value: str,
    expected_user_agent: str,
) -> None:
    from app.chat import router as router_module

    _login(app, user_id)
    received: dict[str, object] = {}

    async def fake_process_chat(**kwargs: object) -> ChatResult:
        received.update(kwargs)
        return ChatResult(1, "answer", datetime(2026, 8, 7, tzinfo=UTC))

    monkeypatch.setattr(router_module, "process_chat", fake_process_chat)

    response = client.post(
        "/api/chat",
        json={"message": "question"},
        headers={"user-agent": header_value},
    )

    assert response.status_code == 200
    assert received["user_agent"] == expected_user_agent


def test_post_chat_requires_login(client: TestClient) -> None:
    response = client.post("/api/chat", json={"message": "question"})

    assert response.status_code == 401
    assert response.json() == {
        "code": "not_authenticated",
        "detail": "로그인이 필요합니다.",
    }


@pytest.mark.parametrize(
    ("payload", "status_code", "detail"),
    [
        ({"message": "   "}, 400, "질문을 입력해주세요."),
        ({"message": "a" * 1001}, 400, "질문은 1000자 이하로 입력해주세요."),
        ({}, 422, "요청 형식이 올바르지 않습니다."),
        ({"message": 1}, 422, "요청 형식이 올바르지 않습니다."),
    ],
)
def test_post_chat_distinguishes_domain_and_request_validation(
    app: FastAPI,
    client: TestClient,
    user_id: int,
    payload: dict[str, object],
    status_code: int,
    detail: str,
) -> None:
    _login(app, user_id)

    response = client.post("/api/chat", json=payload)

    assert response.status_code == status_code
    assert response.json() == {"code": "validation_error", "detail": detail}


def test_post_chat_returns_validation_error_for_malformed_json(
    app: FastAPI,
    client: TestClient,
    user_id: int,
) -> None:
    _login(app, user_id)

    response = client.post(
        "/api/chat",
        content="{",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": "validation_error",
        "detail": "요청 형식이 올바르지 않습니다.",
    }


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (ChatGenerationError(), 502, "openai_api_error"),
        (ChatTimeoutError(), 504, "openai_timeout"),
        (ChatPersistenceError(), 500, "db_save_error"),
        (RuntimeError("select * from secret_cookie"), 500, "internal_error"),
    ],
)
def test_post_chat_returns_safe_error_for_processing_failures(
    app: FastAPI,
    client: TestClient,
    user_id: int,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status_code: int,
    code: str,
) -> None:
    from app.chat import router as router_module

    _login(app, user_id)

    async def failing_process_chat(**_kwargs: object) -> ChatResult:
        raise error

    monkeypatch.setattr(router_module, "process_chat", failing_process_chat)

    response = client.post("/api/chat", json={"message": "question"})

    assert response.status_code == status_code
    assert response.json()["code"] == code
    assert "select" not in response.text
    assert "secret_cookie" not in response.text


def test_unhandled_error_log_hides_internal_error_detail(
    app: FastAPI,
    client: TestClient,
    user_id: int,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.chat import router as router_module

    _login(app, user_id)

    async def failing_process_chat(**_kwargs: object) -> ChatResult:
        raise RuntimeError("select * from secret_cookie")

    monkeypatch.setattr(router_module, "process_chat", failing_process_chat)

    with caplog.at_level("ERROR", logger="app.chat.router"):
        response = client.post("/api/chat", json={"message": "question"})

    assert response.status_code == 500
    assert not caplog.records
    assert "select" not in caplog.text
    assert "secret_cookie" not in caplog.text


def test_non_api_unhandled_error_preserves_framework_server_error(
    app: FastAPI,
    client: TestClient,
) -> None:
    @app.get("/non-api-fail")
    def non_api_fail() -> None:
        raise RuntimeError("non-api failure")

    response = client.get("/non-api-fail")

    assert response.status_code == 500
    assert "internal_error" not in response.text
    assert response.headers.get("content-type", "") != "application/json"


class _AnswerGenerator:
    def __init__(self, error: ChatGenerationError | None = None) -> None:
        self._error = error

    async def generate(self, *, messages: Sequence[ChatMessage]) -> str:
        if self._error is not None:
            raise self._error
        return "answer"


class _SaveFailingRepository(SqlAlchemyChatExchangeRepository):
    def create_success_exchange(self, **_kwargs: object) -> ChatExchange:
        raise RuntimeError("SELECT stack api-key Cookie internal error_message")


def _service_log_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records]


def _assert_safe_request_id_logs(
    messages: list[str], *, request_id: str, expected_events: set[str]
) -> None:
    assert {
        message.split(" request_id=", maxsplit=1)[0] for message in messages
    } == expected_events
    assert all(f"request_id={request_id}" in message for message in messages)
    log_text = "\n".join(messages).lower()
    for secret in (
        "select",
        "stack",
        "key",
        "cookie",
        "internal error_message",
    ):
        assert secret not in log_text


def test_service_success_logs_request_ai_and_db_events_with_request_id(
    db: Session,
    user_id: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    request_id = "safe-success-request"
    service = ChatService(
        db=db,
        repository=SqlAlchemyChatExchangeRepository(db=db),
        answer_generator=_AnswerGenerator(),
    )

    with caplog.at_level("INFO", logger="app.chat.service"):
        asyncio.run(
            service.process_chat(
                user_id=user_id,
                message="SELECT stack api-key Cookie internal error_message",
                request_id=request_id,
                user_agent="Cookie secret",
            )
        )

    _assert_safe_request_id_logs(
        _service_log_messages(caplog),
        request_id=request_id,
        expected_events={
            "request_received",
            "ai_call_started",
            "ai_call_succeeded",
            "db_save_succeeded",
        },
    )


def test_service_failure_logs_safe_ai_and_db_failure_events_with_request_id(
    db: Session,
    user_id: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    request_id = "safe-failure-request"
    service = ChatService(
        db=db,
        repository=_SaveFailingRepository(db=db),
        answer_generator=_AnswerGenerator(),
    )

    with (
        caplog.at_level("INFO", logger="app.chat.service"),
        pytest.raises(ChatPersistenceError),
    ):
        asyncio.run(
            service.process_chat(
                user_id=user_id,
                message="question",
                request_id=request_id,
                user_agent=None,
            )
        )

    _assert_safe_request_id_logs(
        _service_log_messages(caplog),
        request_id=request_id,
        expected_events={
            "request_received",
            "ai_call_started",
            "ai_call_succeeded",
            "db_save_failed",
        },
    )


def test_service_generation_failure_logs_safe_ai_and_db_events_with_request_id(
    db: Session,
    user_id: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    request_id = "safe-generation-failure-request"
    service = ChatService(
        db=db,
        repository=SqlAlchemyChatExchangeRepository(db=db),
        answer_generator=_AnswerGenerator(error=ChatGenerationError()),
    )

    with (
        caplog.at_level("INFO", logger="app.chat.service"),
        pytest.raises(ChatGenerationError),
    ):
        asyncio.run(
            service.process_chat(
                user_id=user_id,
                message="question",
                request_id=request_id,
                user_agent=None,
            )
        )

    _assert_safe_request_id_logs(
        _service_log_messages(caplog),
        request_id=request_id,
        expected_events={
            "request_received",
            "ai_call_started",
            "ai_call_failed",
            "db_save_succeeded",
        },
    )


def test_production_wrapper_logs_request_id_before_validation_failure(
    db: Session,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.chat import service as service_module

    monkeypatch.setattr(service_module, "uuid4", lambda: "wrapper-validation-id")

    with (
        caplog.at_level("INFO", logger="app.chat.service"),
        pytest.raises(ChatValidationError),
    ):
        asyncio.run(
            service_module.process_chat(
                user_id=1,
                message="   ",
                user_agent="Cookie secret",
                db=db,
            )
        )

    assert _service_log_messages(caplog) == [
        "request_received request_id=wrapper-validation-id"
    ]


def test_production_wrapper_logs_safe_request_id_before_client_configuration_failure(
    db: Session,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.chat import service as service_module

    monkeypatch.setattr(service_module, "uuid4", lambda: "wrapper-config-id")

    def fail_client_creation() -> object:
        raise ChatConfigurationError()

    monkeypatch.setattr(service_module, "create_openai_client", fail_client_creation)

    with (
        caplog.at_level("INFO", logger="app.chat.service"),
        pytest.raises(ChatConfigurationError),
    ):
        asyncio.run(
            service_module.process_chat(
                user_id=1,
                message="SELECT stack api-key Cookie internal error_message",
                user_agent="Cookie secret",
                db=db,
            )
        )

    _assert_safe_request_id_logs(
        _service_log_messages(caplog),
        request_id="wrapper-config-id",
        expected_events={"request_received"},
    )


def test_history_is_isolated_and_hides_operational_metadata(
    app: FastAPI,
    client: TestClient,
    db: Session,
    user_id: int,
) -> None:
    other = User(username="history-other", password_hash="hash")
    db.add(other)
    db.commit()
    mine = _add_exchange(
        db,
        user_id=user_id,
        question="my question",
        answer=None,
        status="failed",
        error_message="internal SQL error",
        error_code="internal_error",
        request_id="mine-history",
    )
    _add_exchange(
        db,
        user_id=other.id,
        question="other question",
        answer="other answer",
        status="success",
        request_id="other-history",
    )
    _login(app, user_id)

    response = client.get("/api/chat-exchanges")

    assert response.status_code == 200
    assert response.json() == [
        {
            "chat_exchange_id": mine.id,
            "question": "my question",
            "answer": None,
            "status": "failed",
            "created_at": "2026-08-07T00:00:00Z",
        }
    ]
    assert "error_message" not in response.text
    assert "request_id" not in response.text
    assert "secret-cookie-agent" not in response.text


def test_single_history_hides_other_users_as_not_found(
    app: FastAPI,
    client: TestClient,
    db: Session,
    user_id: int,
) -> None:
    other = User(username="single-other", password_hash="hash")
    db.add(other)
    db.commit()
    exchange = _add_exchange(
        db,
        user_id=other.id,
        question="other question",
        answer="other answer",
        status="success",
        request_id="other-single",
    )
    _login(app, user_id)

    missing = client.get("/api/chat-exchanges/9999")
    foreign = client.get(f"/api/chat-exchanges/{exchange.id}")

    assert missing.status_code == foreign.status_code == 404
    assert (
        missing.json()
        == foreign.json()
        == {
            "code": "conversation_not_found",
            "detail": "대화 기록을 찾을 수 없습니다.",
        }
    )


def test_single_history_non_integer_id_returns_structured_validation_error(
    app: FastAPI,
    client: TestClient,
    user_id: int,
) -> None:
    _login(app, user_id)

    response = client.get("/api/chat-exchanges/not-an-integer")
    openapi = app.openapi()
    response_schema = openapi["paths"]["/api/chat-exchanges/{chat_exchange_id}"]["get"][
        "responses"
    ]["422"]["content"]["application/json"]["schema"]

    assert response.status_code == 422
    assert response.json() == {
        "code": "validation_error",
        "detail": "요청 형식이 올바르지 않습니다.",
    }
    assert response_schema == {"$ref": "#/components/schemas/ErrorResponse"}


@pytest.mark.parametrize(
    ("accept_language", "detail"),
    [
        ("en-US,en;q=0.9", "Please log in."),
        ("ko-KR,ko;q=0.9", "로그인이 필요합니다."),
        ("fr", "로그인이 필요합니다."),
        ("en;q=invalid", "로그인이 필요합니다."),
    ],
)
def test_error_detail_uses_supported_locale_or_korean_fallback(
    client: TestClient,
    accept_language: str,
    detail: str,
) -> None:
    response = client.post(
        "/api/chat",
        json={"message": "question"},
        headers={"accept-language": accept_language},
    )

    assert response.status_code == 401
    assert response.json() == {"code": "not_authenticated", "detail": detail}


def test_missing_english_translation_key_falls_back_to_korean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.chat import i18n

    monkeypatch.delitem(i18n._MESSAGES["en"], "openai_api_error")

    assert (
        i18n.get_message(key="openai_api_error", accept_language="en")
        == "AI 응답 생성에 실패했습니다. 잠시 후 다시 시도해주세요."
    )
