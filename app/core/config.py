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
        hide_input_in_errors=True,
    )

    database_url: str = Field(
        default="sqlite:///./data/chatbot.db",
        validation_alias="DATABASE_URL",
    )
    session_secret: SecretStr = Field(validation_alias="SESSION_SECRET")
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
    )
    openai_model: str = Field(
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

    # OpenAI model은 설정값 자체를 normalize하고 빈 값은 받지 않는다.
    @field_validator("openai_model")
    @classmethod
    def validate_openai_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("OPENAI_MODEL은 비어 있을 수 없습니다.")
        return normalized

    # DATABASE_URL은 명시된 경우 공백 값일 수 없다.
    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("DATABASE_URL은 비어 있을 수 없습니다.")
        return value

    # SESSION_SECRET은 모든 environment에서 실제 application 실행에 필요하다.
    @field_validator("session_secret")
    @classmethod
    def validate_session_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("SESSION_SECRET은 비어 있을 수 없습니다.")
        return value

    # Optional secret은 누락을 허용하되 제공된 공백 값은 받지 않는다.
    @field_validator("openai_api_key", "admin_initial_password")
    @classmethod
    def validate_optional_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            raise ValueError("제공된 secret은 비어 있을 수 없습니다.")
        return value

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

        missing: list[str] = []
        if "database_url" not in self.model_fields_set:
            missing.append("DATABASE_URL")
        if self.openai_api_key is None:
            missing.append("OPENAI_API_KEY")
        if missing:
            raise ValueError(
                "Production 환경에 필요한 설정이 없습니다: " + ", ".join(missing)
            )
        session_secret = self.session_secret.get_secret_value().strip()
        if session_secret == PUBLIC_SESSION_SECRET_PLACEHOLDER:
            raise ValueError(
                "Production 환경에서는 공개된 SESSION_SECRET placeholder를 사용할 수 없습니다."
            )
        return self


settings = Settings()  # pyright: ignore[reportCallIssue]
