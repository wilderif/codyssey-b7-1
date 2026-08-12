"""OpenAI adapter의 request와 안전한 domain 오류 변환을 검증한다."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from openai import APIError, APITimeoutError, AsyncOpenAI
from pydantic import SecretStr

from app.chat.context import ChatMessage
from app.chat.errors import (
    ChatConfigurationError,
    ChatGenerationError,
    ChatInvalidResponseError,
    ChatTimeoutError,
)
from app.chat.openai_client import (
    OpenAIAnswerGenerator,
    create_openai_client,
    get_openai_model,
)
from app.core.config import settings


class FakeCompletions:
    def __init__(self, *, result: object | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


def _create_generator(completions: FakeCompletions) -> OpenAIAnswerGenerator:
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return OpenAIAnswerGenerator(client=cast(AsyncOpenAI, client), model="test-model")


def _run_generate(
    generator: OpenAIAnswerGenerator,
    messages: Sequence[ChatMessage] | None = None,
) -> str:
    return asyncio.run(
        generator.generate(
            messages=messages or [{"role": "user", "content": "question"}]
        )
    )


def test_generate_sends_model_and_messages_once() -> None:
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))]
    )
    completions = FakeCompletions(result=completion)
    generator = _create_generator(completions)
    messages: list[ChatMessage] = [{"role": "user", "content": "question"}]

    answer = _run_generate(generator, messages)

    assert answer == "answer"
    assert completions.calls == [{"model": "test-model", "messages": messages}]


def test_generate_maps_timeout_to_chat_timeout() -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    generator = _create_generator(
        FakeCompletions(error=APITimeoutError(request=request))
    )

    with pytest.raises(ChatTimeoutError):
        _run_generate(generator)


def test_generate_maps_api_error_to_chat_generation_error() -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    generator = _create_generator(
        FakeCompletions(error=APIError("api failed", request=request, body=None))
    )

    with pytest.raises(ChatGenerationError):
        _run_generate(generator)


@pytest.mark.parametrize(
    "completion",
    [
        SimpleNamespace(choices=[]),
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=None))]
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="   "))]
        ),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=1))]),
    ],
)
def test_generate_rejects_response_without_nonblank_text(completion: object) -> None:
    generator = _create_generator(FakeCompletions(result=completion))

    with pytest.raises(ChatInvalidResponseError):
        _run_generate(generator)


def test_openai_configuration_rejects_an_unset_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openai_api_key", None)

    with pytest.raises(ChatConfigurationError):
        create_openai_client()


def test_get_openai_model_returns_the_configured_value_without_revalidation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openai_model", " test-model ")

    assert get_openai_model() == " test-model "


def test_openai_configuration_builds_client_with_retry_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openai_api_key", SecretStr("test-key"))
    monkeypatch.setattr(settings, "openai_model", "test-model")
    monkeypatch.setattr(settings, "openai_timeout_seconds", 17.0)

    client = create_openai_client()
    try:
        assert client.max_retries == 0
        assert client.timeout == 17.0
        assert get_openai_model() == "test-model"
    finally:
        asyncio.run(client.close())
