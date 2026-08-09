"""관리자 운영 metadata 화면의 HTTP layer다."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.admin.errors import AdminReadError
from app.admin.service import list_admin_chat_operation_metadata
from app.auth.dependencies import require_admin
from app.core.database import get_db
from app.core.request_id import get_request_id

router = APIRouter()
logger = logging.getLogger(__name__)
templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent / "ui" / "templates")
)


@router.get("/admin/logs", response_class=HTMLResponse)
def get_admin_logs(
    request: Request,
    _admin_user_id: Annotated[int, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """관리자에게 Chat 운영 metadata 목록을 HTML로 제공한다."""

    try:
        items = list_admin_chat_operation_metadata(db=db)
    except AdminReadError:
        logger.error("admin_read_failed request_id=%s", get_request_id(request))
        return HTMLResponse("서버 오류가 발생했습니다.", status_code=500)
    return templates.TemplateResponse(
        request=request,
        name="admin_logs.html",
        context={"items": items},
    )
