"""공통 UI template과 static style 계약을 검증한다."""

from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.templating import Jinja2Templates

from app.chat.service import ChatExchangeHistoryItem

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


def _history_item(
    *,
    chat_exchange_id: int,
    question: str,
    answer: str | None,
    status: str,
    created_at: datetime,
) -> ChatExchangeHistoryItem:
    return ChatExchangeHistoryItem(
        chat_exchange_id=chat_exchange_id,
        question=question,
        answer=answer,
        status=status,
        created_at=created_at,
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


def test_chat_template_keeps_empty_history_and_complete_form_contract() -> None:
    html = _render_template("chat.html", chat_exchanges=[], is_admin=False)
    collector = _collect_tags(html)
    main = _find_tag(collector, "main", "id", "main-content")
    history = _find_tag(collector, "section", "id", "chat-history")
    empty_state = _find_tag(collector, "p", "id", "chat-empty-state")
    form = _find_tag(collector, "form", "id", "chat-form")
    label = _find_tag(collector, "label", "for", "chat-message")
    textarea = _find_tag(collector, "textarea", "id", "chat-message")
    error = _find_tag(collector, "p", "id", "chat-form-error")
    submit = _find_tag(collector, "button", "id", "chat-submit")
    pending_template = _find_tag(collector, "template", "id", "chat-pending-template")
    logout_form = _find_tag(collector, "form", "action", "/logout")

    assert main is not None
    assert history is not None
    assert empty_state is not None
    assert "아직 대화 기록이 없습니다." in html
    assert "novalidate" in form
    assert label is not None
    assert textarea["maxlength"] == "1000"
    assert textarea["aria-describedby"] == "chat-form-error"
    assert "required" in textarea
    assert error["role"] == "alert"
    assert "hidden" in error
    assert submit["type"] == "submit"
    assert pending_template is not None
    assert logout_form["method"] == "post"
    assert 'href="/admin/logs"' not in html
    assert html.count("<h1") == 1

    for data_hook in (
        "data-chat-question",
        "data-chat-response",
        "data-chat-time",
    ):
        assert any(data_hook in attributes for _, attributes in collector.tags)
    assert any(
        attributes.get("aria-live") == "polite" for _, attributes in collector.tags
    )
    assert "답변 생성 중…" in html


def test_chat_template_renders_history_oldest_first_with_status_and_utc_time() -> None:
    newest = _history_item(
        chat_exchange_id=22,
        question="최신 실패 질문",
        answer=None,
        status="failed",
        created_at=datetime(2026, 8, 10, 15, 45, tzinfo=UTC),
    )
    oldest = _history_item(
        chat_exchange_id=11,
        question="가장 오래된 질문",
        answer="가장 오래된 답변",
        status="success",
        created_at=datetime(2026, 8, 9, 8, 30, 12, tzinfo=UTC),
    )

    html = _render_template(
        "chat.html",
        chat_exchanges=[newest, oldest],
        is_admin=False,
    )
    collector = _collect_tags(html)
    oldest_exchange = _find_tag(
        collector,
        "article",
        "data-chat-exchange-id",
        "11",
    )
    newest_exchange = _find_tag(
        collector,
        "article",
        "data-chat-exchange-id",
        "22",
    )
    rendered_datetimes = [
        attributes["datetime"]
        for tag, attributes in collector.tags
        if tag == "time" and attributes.get("datetime") is not None
    ]

    assert html.index('data-chat-exchange-id="11"') < html.index(
        'data-chat-exchange-id="22"'
    )
    assert html.index("가장 오래된 질문") < html.index("최신 실패 질문")
    assert "chat-exchange--failed" not in (oldest_exchange["class"] or "")
    assert "chat-exchange--failed" in (newest_exchange["class"] or "")
    assert "가장 오래된 답변" in html
    assert "답변을 생성하지 못했습니다." in html
    assert "성공" not in html
    assert oldest.created_at.isoformat() in rendered_datetimes
    assert newest.created_at.isoformat() in rendered_datetimes
    assert html.count("UTC") >= 2


@pytest.mark.parametrize(
    ("is_admin", "admin_link_expected"),
    [(False, False), (True, True)],
)
def test_chat_template_only_renders_admin_navigation_for_admin(
    is_admin: bool,
    admin_link_expected: bool,
) -> None:
    html = _render_template("chat.html", chat_exchanges=[], is_admin=is_admin)

    assert ('href="/admin/logs"' in html) is admin_link_expected
    assert ("관리자 운영 기록" in html) is admin_link_expected


def test_chat_template_escapes_plain_text_and_excludes_internal_metadata() -> None:
    question = '<script>alert("question")</script>\n두 번째 줄\n' + ("긴질문" * 120)
    answer = '<img src=x onerror="alert(1)">\n두 번째 답변'
    internal_sentinels = {
        "error_message": "internal-error-must-not-be-rendered",
        "request_id": "request-id-must-not-be-rendered",
        "user_agent": "user-agent-must-not-be-rendered",
        "password": "password-must-not-be-rendered",
    }
    exchange = {
        "chat_exchange_id": 31,
        "question": question,
        "answer": answer,
        "status": "success",
        "created_at": datetime(2026, 8, 10, 18, tzinfo=UTC),
        **internal_sentinels,
    }

    html = _render_template(
        "chat.html",
        chat_exchanges=[exchange],
        is_admin=False,
        **internal_sentinels,
    )
    collector = _collect_tags(html)

    assert question not in html
    assert answer not in html
    assert "&lt;script&gt;alert(&#34;question&#34;)&lt;/script&gt;" in html
    assert "&lt;img src=x onerror=&#34;alert(1)&#34;&gt;" in html
    assert "두 번째 줄\n" in html
    assert "긴질문" * 120 in html
    assert "두 번째 답변" in html
    for sentinel in internal_sentinels.values():
        assert sentinel not in html
    assert any("data-chat-question" in attributes for _, attributes in collector.tags)
    assert any("data-chat-response" in attributes for _, attributes in collector.tags)
