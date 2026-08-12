"""환경 변수 기반 application 설정을 검증한다."""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

from app.core.config import Settings

pytestmark = pytest.mark.usefixtures("isolated_env_file_directory")


def _production_settings_values(session_secret: str | None) -> dict[str, object]:
    return {
        "APP_ENV": "production",
        "DATABASE_URL": "sqlite:////data/chatbot.db",
        "SESSION_SECRET": session_secret,
        "OPENAI_API_KEY": "test-openai-api-key",
        "OPENAI_MODEL": "test-openai-model",
    }


def _assert_secret_is_masked(
    *,
    configured: Settings,
    secret: str,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    logger = logging.getLogger("tests.core.config")
    caplog.set_level(logging.INFO, logger=logger.name)
    logger.info("settings=%r", configured)
    print(configured)

    assert secret not in repr(configured)
    assert secret not in caplog.text
    assert secret not in capsys.readouterr().out


def _settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]


def test_admin_username_defaults_to_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)

    settings = _settings()

    assert settings.admin_username == "admin"


def test_openai_model_defaults_to_the_documented_cost_focused_model() -> None:
    settings = _settings()

    assert settings.openai_model == "gpt-5-nano"


@pytest.mark.parametrize("session_secret", [None, "", "   "])
def test_session_secret_requires_a_nonblank_value_in_every_environment(
    monkeypatch: pytest.MonkeyPatch,
    session_secret: str | None,
) -> None:
    if session_secret is None:
        monkeypatch.delenv("SESSION_SECRET", raising=False)
    else:
        monkeypatch.setenv("SESSION_SECRET", session_secret)

    with pytest.raises(ValidationError, match="SESSION_SECRET"):
        _settings()


def test_session_secret_accepts_a_nonblank_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SESSION_SECRET", "valid-session-secret")

    configured = _settings()

    assert configured.session_secret.get_secret_value() == "valid-session-secret"


@pytest.mark.parametrize("api_key", ["", "   "])
def test_local_rejects_a_blank_provided_openai_api_key(api_key: str) -> None:
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        Settings.model_validate(
            {"SESSION_SECRET": "valid-session-secret", "OPENAI_API_KEY": api_key}
        )


def test_local_allows_an_unset_openai_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    configured = Settings.model_validate({"SESSION_SECRET": "valid-session-secret"})

    assert configured.openai_api_key is None


def test_local_accepts_a_nonblank_openai_api_key() -> None:
    configured = Settings.model_validate(
        {
            "SESSION_SECRET": "valid-session-secret",
            "OPENAI_API_KEY": "test-openai-api-key",
        }
    )

    assert configured.openai_api_key is not None
    assert configured.openai_api_key.get_secret_value() == "test-openai-api-key"


@pytest.mark.parametrize("model", ["", "   "])
def test_openai_model_rejects_blank_values(model: str) -> None:
    with pytest.raises(ValidationError, match="OPENAI_MODEL"):
        Settings.model_validate(
            {"SESSION_SECRET": "valid-session-secret", "OPENAI_MODEL": model}
        )


def test_openai_model_normalizes_a_configured_value() -> None:
    configured = Settings.model_validate(
        {"SESSION_SECRET": "valid-session-secret", "OPENAI_MODEL": " test-model "}
    )

    assert configured.openai_model == "test-model"


def test_local_database_url_defaults_to_sqlite() -> None:
    configured = Settings.model_validate({"SESSION_SECRET": "valid-session-secret"})

    assert configured.database_url == "sqlite:///./data/chatbot.db"


@pytest.mark.parametrize("database_url", ["", "   "])
def test_database_url_rejects_blank_explicit_values(database_url: str) -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings.model_validate(
            {"SESSION_SECRET": "valid-session-secret", "DATABASE_URL": database_url}
        )


@pytest.mark.parametrize(
    ("configured_timeout", "expected_timeout"),
    [("1", 1.0), ("0.25", 0.25)],
)
def test_openai_timeout_converts_positive_environment_values(
    monkeypatch: pytest.MonkeyPatch,
    configured_timeout: str,
    expected_timeout: float,
) -> None:
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", configured_timeout)

    settings = _settings()

    assert settings.openai_timeout_seconds == expected_timeout


@pytest.mark.parametrize("configured_timeout", ["0", "-1", "not-a-number"])
def test_openai_timeout_rejects_nonpositive_or_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    configured_timeout: str,
) -> None:
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", configured_timeout)

    with pytest.raises(ValidationError):
        _settings()


def test_environment_and_log_level_normalize_case_insensitively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "LOCAL")
    monkeypatch.setenv("LOG_LEVEL", "warning")

    settings = _settings()

    assert settings.app_env == "local"
    assert settings.log_level == "WARNING"


@pytest.mark.parametrize(
    ("configured_username", "expected_username"),
    [
        ("  admin  ", "admin"),
        ("  ops-admin  ", "ops-admin"),
        ("root", "root"),
    ],
)
def test_admin_username_accepts_trimmed_valid_values(
    monkeypatch: pytest.MonkeyPatch,
    configured_username: str,
    expected_username: str,
) -> None:
    monkeypatch.setenv("ADMIN_USERNAME", configured_username)

    settings = _settings()

    assert settings.admin_username == expected_username


@pytest.mark.parametrize(
    "username",
    ["", "   ", "ab", "a" * 31],
)
def test_admin_username_rejects_blank_and_out_of_range_values(
    monkeypatch: pytest.MonkeyPatch,
    username: str,
) -> None:
    monkeypatch.setenv("ADMIN_USERNAME", username)

    with pytest.raises(ValidationError):
        _settings()


def test_admin_initial_password_allows_unset_and_rejects_blank_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ADMIN_INITIAL_PASSWORD", raising=False)

    without_password = _settings()

    assert without_password.admin_initial_password is None

    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "")
    with pytest.raises(ValidationError, match="ADMIN_INITIAL_PASSWORD"):
        _settings()


def test_admin_initial_password_does_not_apply_auth_password_length_policy() -> None:
    configured = Settings.model_validate(
        {
            "SESSION_SECRET": "valid-session-secret",
            "ADMIN_INITIAL_PASSWORD": "seven77",
        }
    )

    assert configured.admin_initial_password is not None
    assert configured.admin_initial_password.get_secret_value() == "seven77"


def test_admin_initial_password_is_masked_in_repr_log_console_and_validation_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "initial-password-must-not-appear"
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", secret)
    configured = _settings()

    _assert_secret_is_masked(
        configured=configured,
        secret=secret,
        caplog=caplog,
        capsys=capsys,
    )

    monkeypatch.setenv("ADMIN_USERNAME", " ")
    with pytest.raises(ValidationError) as error:
        _settings()

    assert secret not in str(error.value)


@pytest.mark.parametrize(
    "session_secret",
    [
        "change-me-for-local-development",
        " change-me-for-local-development",
        "change-me-for-local-development ",
        " change-me-for-local-development ",
    ],
)
def test_production_rejects_public_session_secret_placeholder(
    session_secret: str,
) -> None:
    with pytest.raises(ValidationError, match="SESSION_SECRET"):
        Settings.model_validate(_production_settings_values(session_secret))


def test_production_rejects_missing_database_url() -> None:
    values = _production_settings_values("valid-session-secret")
    del values["DATABASE_URL"]

    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings.model_validate(values)


def test_production_rejects_missing_openai_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    values = _production_settings_values("valid-session-secret")
    del values["OPENAI_API_KEY"]

    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        Settings.model_validate(values)


def test_production_accepts_configured_session_secret() -> None:
    configured = Settings.model_validate(
        _production_settings_values("private-session-secret-value")
    )

    assert configured.app_env == "production"
    assert (
        configured.session_secret.get_secret_value() == "private-session-secret-value"
    )


def test_session_secret_is_masked_in_repr_log_and_production_validation_error(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "private-session-secret-value-must-not-appear"
    configured = Settings.model_validate({"APP_ENV": "local", "SESSION_SECRET": secret})

    _assert_secret_is_masked(
        configured=configured,
        secret=secret,
        caplog=caplog,
        capsys=capsys,
    )

    values = _production_settings_values(secret)
    values["OPENAI_API_KEY"] = None

    with pytest.raises(ValidationError) as error:
        Settings.model_validate(values)

    assert secret not in str(error.value)
