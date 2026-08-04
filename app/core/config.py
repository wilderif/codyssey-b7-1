"""Application settings loaded from environment variables."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    openai_model: str | None = Field(default=None, validation_alias="OPENAI_MODEL")
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

    @field_validator("app_env", mode="before")
    @classmethod
    def normalize_app_env(cls, value: object) -> object:
        return value.lower() if isinstance(value, str) else value

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("openai_timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("OPENAI_TIMEOUT_SECONDS는 0보다 커야 합니다.")
        return value

    @model_validator(mode="after")
    def validate_production_settings(self) -> Self:
        if self.app_env != "production":
            return self

        required = {
            "SESSION_SECRET": self.session_secret,
            "OPENAI_API_KEY": self.openai_api_key,
            "OPENAI_MODEL": self.openai_model,
        }
        missing = [name for name, value in required.items() if _is_blank(value)]
        if missing:
            raise ValueError(
                "Production 환경에 필요한 설정이 없습니다: " + ", ".join(missing)
            )
        return self


def _is_blank(value: SecretStr | str | None) -> bool:
    if value is None:
        return True
    if isinstance(value, SecretStr):
        return not value.get_secret_value().strip()
    return not value.strip()


settings = Settings()
