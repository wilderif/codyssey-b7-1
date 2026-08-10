"""Auth use case와 User transaction을 처리한다."""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import NoReturn

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.models import ADMIN_ROLE, User
from app.auth.repository import create_user, get_admin_user, get_user_by_username
from app.core.config import Settings
from app.core.security import hash_password, verify_password

MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 30
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 72

logger = logging.getLogger(__name__)


class RegistrationReason(StrEnum):
    """회원가입이 실패한 안전한 domain reason이다."""

    USERNAME_LENGTH = "username_length"
    PASSWORD_LENGTH = "password_length"
    DUPLICATE_USERNAME = "duplicate_username"


class RegistrationError(Exception):
    """UI가 안전한 회원가입 오류 message로 변환할 수 있는 예외다."""

    def __init__(self, reason: RegistrationReason) -> None:
        self.reason = reason
        super().__init__(reason.value)


class AdminBootstrapReason(StrEnum):
    """Initial admin 생성이 실패한 안전한 startup reason이다."""

    MISSING_INITIAL_PASSWORD = "missing_initial_password"
    INVALID_INITIAL_PASSWORD = "invalid_initial_password"
    INVALID_ADMIN_ROLE = "invalid_admin_role"
    DB_ERROR = "db_error"


class AdminBootstrapError(RuntimeError):
    """Application startup을 중단하는 안전한 initial admin 오류다."""

    def __init__(self, reason: AdminBootstrapReason) -> None:
        self.reason = reason
        super().__init__(reason.value)


def authenticate_user(
    *,
    db: Session,
    username: str,
    password: str,
) -> User | None:
    """Username과 password가 일치하는 User를 반환한다."""

    user = get_user_by_username(db=db, username=username.strip())
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def register_user(*, db: Session, username: str, password: str) -> User:
    """회원가입 입력을 검증하고 일반 사용자 계정을 저장한다."""

    normalized_username = username.strip()
    _validate_registration_input(
        username=normalized_username,
        password=password,
    )

    try:
        if get_user_by_username(db=db, username=normalized_username) is not None:
            raise RegistrationError(RegistrationReason.DUPLICATE_USERNAME)

        user = create_user(
            db=db,
            username=normalized_username,
            password_hash=hash_password(password),
        )
        db.commit()
    except RegistrationError:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise RegistrationError(RegistrationReason.DUPLICATE_USERNAME) from None
    except Exception:
        db.rollback()
        raise

    return user


def ensure_initial_admin(*, db: Session, app_settings: Settings) -> None:
    """초기 admin 계정을 필요할 때 한 번만 생성한다."""

    try:
        existing_admin = get_admin_user(db=db)
    except Exception:  # noqa: BLE001 - startup 경계에서 내부 DB 오류를 숨긴다.
        db.rollback()
        _raise_admin_bootstrap_error(AdminBootstrapReason.DB_ERROR)

    if existing_admin is not None:
        db.rollback()
        return

    try:
        bootstrap_username_owner = get_user_by_username(
            db=db,
            username=app_settings.admin_username,
        )
    except Exception:  # noqa: BLE001 - startup 경계에서 내부 DB 오류를 숨긴다.
        db.rollback()
        _raise_admin_bootstrap_error(AdminBootstrapReason.DB_ERROR)

    if bootstrap_username_owner is not None:
        db.rollback()
        _raise_admin_bootstrap_error(AdminBootstrapReason.INVALID_ADMIN_ROLE)

    initial_password = app_settings.admin_initial_password
    if initial_password is None:
        db.rollback()
        _raise_admin_bootstrap_error(AdminBootstrapReason.MISSING_INITIAL_PASSWORD)

    password = initial_password.get_secret_value()
    if not _is_valid_password_length(password):
        db.rollback()
        _raise_admin_bootstrap_error(AdminBootstrapReason.INVALID_INITIAL_PASSWORD)

    try:
        create_user(
            db=db,
            username=app_settings.admin_username,
            password_hash=hash_password(password),
            role=ADMIN_ROLE,
        )
        db.commit()
    except Exception:  # noqa: BLE001 - startup 경계에서 내부 DB·hash 오류를 숨긴다.
        db.rollback()
        _raise_admin_bootstrap_error(AdminBootstrapReason.DB_ERROR)


def _validate_registration_input(*, username: str, password: str) -> None:
    if not MIN_USERNAME_LENGTH <= len(username) <= MAX_USERNAME_LENGTH:
        raise RegistrationError(RegistrationReason.USERNAME_LENGTH)
    if not _is_valid_password_length(password):
        raise RegistrationError(RegistrationReason.PASSWORD_LENGTH)


def _is_valid_password_length(password: str) -> bool:
    return MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH


def _raise_admin_bootstrap_error(reason: AdminBootstrapReason) -> NoReturn:
    logger.error("admin_bootstrap_failed reason=%s", reason.value)
    raise AdminBootstrapError(reason) from None
