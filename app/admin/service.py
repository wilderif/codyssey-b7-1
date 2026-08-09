"""관리자 운영 metadata read use case다."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.admin.errors import AdminReadError
from app.admin.repository import (
    AdminChatOperationMetadataRow,
    AdminRepository,
    SqlAlchemyAdminRepository,
)
from app.admin.schemas import AdminChatOperationMetadataItem


def list_admin_chat_operation_metadata(
    *,
    db: Session,
) -> list[AdminChatOperationMetadataItem]:
    """관리자 화면에 안전한 운영 metadata만 최신순으로 제공한다."""

    repository: AdminRepository = SqlAlchemyAdminRepository(db=db)
    try:
        rows = repository.list_chat_operation_metadata()
    except Exception as error:
        db.rollback()
        raise AdminReadError from error

    return [_to_metadata_item(row) for row in rows]


def _to_metadata_item(
    row: AdminChatOperationMetadataRow,
) -> AdminChatOperationMetadataItem:
    return AdminChatOperationMetadataItem(
        user_id=row.user_id,
        username=row.username,
        chat_exchange_id=row.chat_exchange_id,
        created_at=row.created_at,
        request_id=row.request_id,
        user_agent=row.user_agent,
        response_time_ms=row.response_time_ms,
        status=row.status,
        error_code=row.error_code,
    )
