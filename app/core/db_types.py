"""SQLAlchemy model이 공유하는 database type과 default factory다."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator

UTC_TIMEZONE = UTC
TIMEZONE_AWARE_REQUIRED_ERROR = "created_at must be timezone-aware"


def utc_now() -> datetime:
    """UTC timezone 정보를 포함한 현재 시각을 반환한다."""

    return datetime.now(UTC_TIMEZONE)


class UTCDateTime(TypeDecorator[datetime]):
    """SQLite에서도 UTC timezone 정보를 복원하는 datetime type이다."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self,
        value: datetime | None,
        dialect: object,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(TIMEZONE_AWARE_REQUIRED_ERROR)
        return value.astimezone(UTC_TIMEZONE)

    def process_result_value(
        self,
        value: datetime | None,
        dialect: object,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC_TIMEZONE)
        return value.astimezone(UTC_TIMEZONE)
