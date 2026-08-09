"""환경 변수 기반 application 설정을 검증한다."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings


@pytest.fixture(autouse=True)
def use_empty_env_file_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)


def test_admin_username_defaults_to_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)

    settings = Settings()

    assert settings.admin_username == "admin"


def test_admin_username_uses_trimmed_environment_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ADMIN_USERNAME", "  configured-admin  ")

    settings = Settings()

    assert settings.admin_username == "configured-admin"


@pytest.mark.parametrize("username", ["", "   ", "ab", "a" * 31])
def test_admin_username_rejects_blank_or_out_of_range_values(
    monkeypatch: pytest.MonkeyPatch,
    username: str,
) -> None:
    monkeypatch.setenv("ADMIN_USERNAME", username)

    with pytest.raises(ValidationError):
        Settings()


def test_admin_initial_password_distinguishes_unset_and_blank_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ADMIN_INITIAL_PASSWORD", raising=False)

    without_password = Settings()

    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "")
    with_blank_password = Settings()

    assert without_password.admin_initial_password is None
    assert isinstance(with_blank_password.admin_initial_password, SecretStr)
    assert with_blank_password.admin_initial_password.get_secret_value() == ""


def test_admin_initial_password_is_masked_in_repr_log_console_and_validation_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "initial-password-must-not-appear"
    logger = logging.getLogger("tests.core.config")
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", secret)
    configured = Settings()

    caplog.set_level(logging.INFO, logger=logger.name)
    logger.info("settings=%r", configured)
    print(configured)

    assert secret not in repr(configured)
    assert secret not in caplog.text
    assert secret not in capsys.readouterr().out

    monkeypatch.setenv("ADMIN_USERNAME", " ")
    with pytest.raises(ValidationError) as error:
        Settings()

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


def test_production_rejects_missing_session_secret() -> None:
    values = _production_settings_values("valid-session-secret")
    del values["SESSION_SECRET"]

    with pytest.raises(ValidationError, match="SESSION_SECRET"):
        Settings.model_validate(values)


@pytest.mark.parametrize("session_secret", [None, "", "   "])
def test_production_rejects_blank_session_secret(
    session_secret: str | None,
) -> None:
    with pytest.raises(ValidationError, match="SESSION_SECRET"):
        Settings.model_validate(_production_settings_values(session_secret))


def test_production_accepts_configured_session_secret() -> None:
    configured = Settings.model_validate(
        _production_settings_values("private-session-secret-value")
    )

    assert configured.app_env == "production"
    assert configured.session_secret is not None
    assert (
        configured.session_secret.get_secret_value() == "private-session-secret-value"
    )


@pytest.mark.parametrize(
    "session_secret",
    [None, "", "   ", "change-me-for-local-development"],
)
def test_local_allows_session_secret_values_rejected_only_in_production(
    session_secret: str | None,
) -> None:
    configured = Settings.model_validate(
        {"APP_ENV": "local", "SESSION_SECRET": session_secret}
    )

    assert configured.app_env == "local"


def test_session_secret_is_masked_in_repr_log_and_production_validation_error(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "private-session-secret-value-must-not-appear"
    logger = logging.getLogger("tests.core.config")
    configured = Settings.model_validate({"APP_ENV": "local", "SESSION_SECRET": secret})

    caplog.set_level(logging.INFO, logger=logger.name)
    logger.info("settings=%r", configured)
    print(configured)

    assert secret not in repr(configured)
    assert secret not in caplog.text
    assert secret not in capsys.readouterr().out

    values = _production_settings_values(secret)
    values["OPENAI_API_KEY"] = None

    with pytest.raises(ValidationError) as error:
        Settings.model_validate(values)

    assert secret not in str(error.value)


def _production_settings_values(session_secret: str | None) -> dict[str, object]:
    return {
        "APP_ENV": "production",
        "SESSION_SECRET": session_secret,
        "OPENAI_API_KEY": "test-openai-api-key",
        "OPENAI_MODEL": "test-openai-model",
    }
