"""공통 UI template과 static style 계약을 검증한다."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIRECTORY = PROJECT_ROOT / "app" / "ui" / "templates"
STYLES_PATH = PROJECT_ROOT / "app" / "ui" / "static" / "styles.css"
templates = Jinja2Templates(directory=str(TEMPLATE_DIRECTORY))


def _render_template(name: str, **context: object) -> str:
    return templates.get_template(name).render(**context)


def test_base_template_defines_shared_document_foundation() -> None:
    html = _render_template("base.html")

    for expected_markup in (
        '<html lang="ko">',
        '<meta charset="utf-8">',
        'name="viewport" content="width=device-width, initial-scale=1"',
        "<title>Codyssey</title>",
        '<link rel="stylesheet" href="/static/styles.css">',
        '<a class="skip-link" href="#main-content">본문으로 건너뛰기</a>',
    ):
        assert expected_markup in html


def test_shared_styles_support_responsive_keyboard_accessible_layout() -> None:
    styles = STYLES_PATH.read_text(encoding="utf-8")

    for expected_rule in (
        "box-sizing: border-box",
        "overflow-wrap: anywhere",
        ":focus-visible",
        ".skip-link:focus",
        "width: min(100%, 28rem)",
        "@media (max-width: 30rem)",
    ):
        assert expected_rule in styles
