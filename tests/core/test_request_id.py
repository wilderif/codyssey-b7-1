"""HTTP request ID middleware interface를 검증한다."""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.request_id import (
    REQUEST_ID_HEADER,
    RequestIdMiddleware,
    get_request_id,
)


def test_request_id_is_server_generated_and_shared_with_response() -> None:
    application = FastAPI()
    application.add_middleware(RequestIdMiddleware)

    @application.get("/request-id")
    def read_request_id(request: Request) -> dict[str, str]:
        return {"request_id": get_request_id(request)}

    client = TestClient(application)
    response = client.get(
        "/request-id",
        headers={REQUEST_ID_HEADER: "client-controlled-request-id"},
    )

    request_id = response.json()["request_id"]
    assert UUID(request_id).version == 4
    assert response.headers[REQUEST_ID_HEADER] == request_id
    assert request_id != "client-controlled-request-id"


def test_get_request_id_fails_when_middleware_is_missing() -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "state": {},
        }
    )

    with pytest.raises(RuntimeError, match="RequestIdMiddleware"):
        get_request_id(request)
