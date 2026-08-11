"""UI template 환경과 화면 전용 formatting을 제공한다."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.templating import Jinja2Templates

_TEMPLATE_DIRECTORY = Path(__file__).parent / "templates"
_KST = timezone(timedelta(hours=9), name="KST")


def format_kst_datetime(value: datetime) -> str:
    """Timezone-aware datetime을 고정된 KST 화면 문자열로 변환한다."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("화면 시각은 timezone-aware datetime이어야 합니다.")

    return f"{value.astimezone(_KST):%Y-%m-%d %H:%M:%S} KST"


templates = Jinja2Templates(directory=str(_TEMPLATE_DIRECTORY))
templates.env.filters["kst_datetime"] = format_kst_datetime
