"""공통 UI template과 static style 계약을 검증한다."""

from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.templating import Jinja2Templates

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIRECTORY = PROJECT_ROOT / "app" / "ui" / "templates"
STYLES_PATH = PROJECT_ROOT / "app" / "ui" / "static" / "styles.css"
templates = Jinja2Templates(directory=str(TEMPLATE_DIRECTORY))


class StartTagCollector(HTMLParser):
    """Rendering된 HTML의 시작 tag와 attribute를 수집한다."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.tags.append((tag, dict(attrs)))


def _render_template(name: str, **context: object) -> str:
    return templates.get_template(name).render(**context)


def _collect_tags(html: str) -> StartTagCollector:
    collector = StartTagCollector()
    collector.feed(html)
    return collector


def _find_tag(
    collector: StartTagCollector,
    tag_name: str,
    attribute_name: str,
    attribute_value: str,
) -> dict[str, str | None]:
    return next(
        attributes
        for tag, attributes in collector.tags
        if tag == tag_name and attributes.get(attribute_name) == attribute_value
    )


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


@pytest.mark.parametrize(
    (
        "template_name",
        "action",
        "heading",
        "alternative_href",
        "username_autocomplete",
        "password_autocomplete",
        "username_minlength",
        "password_minlength",
    ),
    [
        (
            "signup.html",
            "/signup",
            "회원가입",
            "/login",
            "username",
            "new-password",
            "3",
            "8",
        ),
        (
            "login.html",
            "/login",
            "Login",
            "/signup",
            "username",
            "current-password",
            None,
            None,
        ),
    ],
)
def test_auth_template_defines_form_contract(
    template_name: str,
    action: str,
    heading: str,
    alternative_href: str,
    username_autocomplete: str,
    password_autocomplete: str,
    username_minlength: str | None,
    password_minlength: str | None,
) -> None:
    html = _render_template(template_name, error=None, username="")
    collector = _collect_tags(html)
    form = _find_tag(collector, "form", "action", action)
    username = _find_tag(collector, "input", "name", "username")
    password = _find_tag(collector, "input", "name", "password")

    assert form["method"] == "post"
    assert username["type"] == "text"
    assert username["value"] == ""
    assert username["maxlength"] == "30"
    assert username["autocomplete"] == username_autocomplete
    assert username.get("minlength") == username_minlength
    assert "required" in username
    assert password["type"] == "password"
    assert password["maxlength"] == "72"
    assert password["autocomplete"] == password_autocomplete
    assert password.get("minlength") == password_minlength
    assert "required" in password
    assert "value" not in password
    assert f'<h1 id="{action[1:]}-heading">{heading}</h1>' in html
    assert f'<a href="{alternative_href}">' in html
    assert '<link rel="stylesheet" href="/static/styles.css">' in html
    assert 'role="alert"' not in html


@pytest.mark.parametrize(
    ("template_name", "error_id"),
    [("signup.html", "signup-error"), ("login.html", "login-error")],
)
def test_auth_template_safely_renders_error_and_username_without_password(
    template_name: str,
    error_id: str,
) -> None:
    raw_username = '<script>alert("username")</script>'
    raw_error = '<img src=x onerror="alert(1)">'
    password = "password-must-not-be-rendered"

    html = _render_template(
        template_name,
        error=raw_error,
        username=raw_username,
        password=password,
    )
    collector = _collect_tags(html)
    alert = _find_tag(collector, "p", "id", error_id)
    username = _find_tag(collector, "input", "name", "username")
    password_input = _find_tag(collector, "input", "name", "password")

    assert alert["role"] == "alert"
    assert username["aria-describedby"] == error_id
    assert password_input["aria-describedby"] == error_id
    assert username["value"] == raw_username
    assert "value" not in password_input
    assert raw_username not in html
    assert raw_error not in html
    assert password not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img src=x onerror=&#34;alert(1)&#34;&gt;" in html
