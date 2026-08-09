"""관리자 운영 metadata 화면의 HTTP layer다."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.admin.service import list_admin_chat_operation_metadata
from app.auth.dependencies import require_admin
from app.core.database import get_db

router = APIRouter()
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

    items = list_admin_chat_operation_metadata(db=db)
    return templates.TemplateResponse(
        request=request,
        name="admin_logs.html",
        context={"items": items},
    )
