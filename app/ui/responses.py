"""Browser cache에 민감한 UI response helper를 제공한다."""

from __future__ import annotations

from typing import TypeVar

from fastapi import Response

_NO_STORE = "no-store"
ResponseT = TypeVar("ResponseT", bound=Response)


def prevent_browser_caching(response: ResponseT) -> ResponseT:
    """동적 인증 화면이 HTTP cache에 저장되지 않도록 표시한다."""

    response.headers["Cache-Control"] = _NO_STORE
    return response
