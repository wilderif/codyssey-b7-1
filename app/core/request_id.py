"""HTTP request 추적 ID를 생성하고 전달한다."""

from __future__ import annotations

import logging
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_STATE_KEY = "request_id"

logger = logging.getLogger(__name__)


class RequestIdMiddleware:
    """각 HTTP request에 server-generated request ID를 부여한다."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid4())
        scope.setdefault("state", {})[REQUEST_ID_STATE_KEY] = request_id
        if scope["method"] == "POST" and scope["path"] == "/api/chat":
            logger.info("request_received request_id=%s", request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
            await send(message)

        await self.app(scope, receive, send_with_request_id)


def get_request_id(request: Request) -> str:
    """middleware가 생성한 현재 HTTP request ID를 반환한다."""

    request_id = getattr(request.state, REQUEST_ID_STATE_KEY, None)
    if not isinstance(request_id, str) or not request_id:
        raise RuntimeError("RequestIdMiddleware가 등록되지 않았습니다.")
    return request_id
