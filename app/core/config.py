"""Application settings loaded from environment variables."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PUBLIC_SESSION_SECRET_PLACEHOLDER = "change-me-for-local-development"


class Settings(BaseSettings):
    """공용 application 설정이다."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="sqlite:///./data/chatbot.db",
        validation_alias="DATABASE_URL",
    )
    session_secret: SecretStr | None = Field(
        default=None,
        validation_alias="SESSION_SECRET",
    )
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
    )
    openai_model: str | None = Field(
        default="gpt-5-nano",
        validation_alias="OPENAI_MODEL",
    )
    openai_timeout_seconds: float = Field(
        default=30,
        validation_alias="OPENAI_TIMEOUT_SECONDS",
    )
    app_env: Literal["local", "production"] = Field(
        default="local",
        validation_alias="APP_ENV",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        validation_alias="LOG_LEVEL",
    )
    admin_username: str = Field(
        default="admin",
        min_length=3,
        max_length=30,
        validation_alias="ADMIN_USERNAME",
    )
    admin_initial_password: SecretStr | None = Field(
        default=None,
        validation_alias="ADMIN_INITIAL_PASSWORD",
    )

    # APP_ENV는 대소문자 상관없이 받는다.
    @field_validator("app_env", mode="before")
    @classmethod
    def normalize_app_env(cls, value: object) -> object:
        return value.lower() if isinstance(value, str) else value

    # LOG_LEVEL도 소문자로 넣어도 되게 한다.
    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    # 값 검사 전에 ADMIN_USERNAME 앞뒤 공백을 없앤다.
    @field_validator("admin_username", mode="before")
    @classmethod
    def normalize_admin_username(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    # timeout은 0 이하로 못 넣게 막는다.
    @field_validator("openai_timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("OPENAI_TIMEOUT_SECONDS는 0보다 커야 합니다.")
        return value

    # production일 때 꼭 필요한 설정들이 있는지 본다.
    @model_validator(mode="after")
    def validate_production_settings(self) -> Self:
        if self.app_env != "production":
            return self

        required = {
            "DATABASE_URL": (
                self.database_url if "database_url" in self.model_fields_set else None
            ),
            "SESSION_SECRET": self.session_secret,
            "OPENAI_API_KEY": self.openai_api_key,
            "OPENAI_MODEL": self.openai_model,
        }
        missing = [name for name, value in required.items() if _is_blank(value)]
        if missing:
            raise ValueError(
                "Production 환경에 필요한 설정이 없습니다: " + ", ".join(missing)
            )
        if self.session_secret is not None:
            session_secret = self.session_secret.get_secret_value().strip()
            if session_secret == PUBLIC_SESSION_SECRET_PLACEHOLDER:
                raise ValueError(
                    "Production 환경에서는 공개된 SESSION_SECRET placeholder를 사용할 수 없습니다."
                )
        return self


def _is_blank(value: SecretStr | str | None) -> bool:
    if value is None:
        return True
    if isinstance(value, SecretStr):
        return not value.get_secret_value().strip()
    return not value.strip()


settings = Settings()
