"""OpenAI SDK 호출을 Chat domain의 answer 생성 계약으로 감싼다."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from openai import APIError, APITimeoutError, AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from app.chat.context import ChatMessage
from app.chat.errors import (
    ChatConfigurationError,
    ChatGenerationError,
    ChatInvalidResponseError,
    ChatTimeoutError,
)
from app.core.config import settings


class OpenAIAnswerGenerator:
    """OpenAI Chat Completions로 text answer를 생성한다."""

    def __init__(self, *, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def generate(self, *, messages: Sequence[ChatMessage]) -> str:
        """message 목록을 한 번 전송하고 비어 있지 않은 answer를 반환한다."""

        try:
            completion = await self._client.chat.completions.create(
                model=self._model,
                messages=cast(
                    list[ChatCompletionMessageParam],
                    list(messages),
                ),
            )
        except APITimeoutError as error:
            raise ChatTimeoutError() from error
        except APIError as error:
            raise ChatGenerationError() from error

        if not completion.choices:
            raise ChatInvalidResponseError()

        answer = completion.choices[0].message.content
        if not isinstance(answer, str) or not answer.strip():
            raise ChatInvalidResponseError()
        return answer


def create_openai_client() -> AsyncOpenAI:
    """공용 settings로 timeout과 retry 정책이 반영된 client를 생성한다."""

    api_key = settings.openai_api_key
    model = settings.openai_model
    if (
        api_key is None
        or not api_key.get_secret_value().strip()
        or model is None
        or not model.strip()
    ):
        raise ChatConfigurationError()

    return AsyncOpenAI(
        api_key=api_key.get_secret_value(),
        timeout=settings.openai_timeout_seconds,
        max_retries=0,
    )


def get_openai_model() -> str:
    """검증된 OpenAI model 이름을 반환한다."""

    model = settings.openai_model
    if model is None or not model.strip():
        raise ChatConfigurationError()
    return model.strip()
