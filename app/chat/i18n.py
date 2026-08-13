"""Chat JSON API의 안전한 오류 message 번역을 제공한다."""

from __future__ import annotations

import re

DEFAULT_LOCALE = "ko"
SUPPORTED_LOCALES = frozenset({"ko", "en"})

_MESSAGES = {
    "ko": {
        "validation_error": "요청 형식이 올바르지 않습니다.",
        "empty_message": "질문을 입력해주세요.",
        "message_too_long": "질문은 1000자 이하로 입력해주세요.",
        "not_authenticated": "로그인이 필요합니다.",
        "forbidden": "접근 권한이 없습니다.",
        "conversation_not_found": "대화 기록을 찾을 수 없습니다.",
        "internal_error": "서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        "openai_api_error": "AI 응답 생성에 실패했습니다. 잠시 후 다시 시도해주세요.",
        "openai_timeout": "AI 응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.",
    },
    "en": {
        "validation_error": "The request format is invalid.",
        "empty_message": "Please enter a question.",
        "message_too_long": "Questions must be 1000 characters or fewer.",
        "not_authenticated": "Please log in.",
        "forbidden": "You do not have permission to access this resource.",
        "conversation_not_found": "Conversation not found.",
        "internal_error": "A server error occurred. Please try again later.",
        "openai_api_error": "Failed to generate an AI response. Please try again later.",
        "openai_timeout": "The AI response timed out. Please try again later.",
    },
}
_LANGUAGE_RANGE = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")


def get_locale(accept_language: str | None) -> str:
    """Accept-Language에서 지원 locale을 선택하고 실패 시 Korean을 반환한다."""

    if not accept_language:
        return DEFAULT_LOCALE

    candidates: list[tuple[float, int, str]] = []
    for index, item in enumerate(accept_language.split(",")):
        parts = [part.strip() for part in item.split(";")]
        language_range = parts[0]
        if not _LANGUAGE_RANGE.fullmatch(language_range):
            return DEFAULT_LOCALE
        quality = 1.0
        for parameter in parts[1:]:
            key, separator, value = parameter.partition("=")
            if separator != "=" or key.lower() != "q":
                return DEFAULT_LOCALE
            try:
                quality = float(value)
            except ValueError:
                return DEFAULT_LOCALE
            if not 0 <= quality <= 1:
                return DEFAULT_LOCALE
        locale = language_range.split("-", maxsplit=1)[0].lower()
        if locale in SUPPORTED_LOCALES and quality > 0:
            candidates.append((quality, -index, locale))
    if not candidates:
        return DEFAULT_LOCALE
    return max(candidates)[2]


def get_message(*, key: str, accept_language: str | None) -> str:
    """번역 key가 없거나 해석이 실패해도 Korean 안전 message를 반환한다."""

    locale = get_locale(accept_language)
    return _MESSAGES.get(locale, {}).get(
        key,
        _MESSAGES[DEFAULT_LOCALE].get(key, _MESSAGES[DEFAULT_LOCALE]["internal_error"]),
    )
