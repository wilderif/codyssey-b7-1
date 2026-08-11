"""UI template 환경과 화면 전용 formatting을 제공한다."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

_TEMPLATE_DIRECTORY = Path(__file__).parent / "templates"


templates = Jinja2Templates(directory=str(_TEMPLATE_DIRECTORY))
