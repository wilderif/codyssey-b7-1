"""Auth use case와 User transaction을 처리한다."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.repository import create_user, get_user_by_username
from app.core.security import hash_password, verify_password

MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 30
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 72


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


def _validate_registration_input(*, username: str, password: str) -> None:
    if not MIN_USERNAME_LENGTH <= len(username) <= MAX_USERNAME_LENGTH:
        raise RegistrationError(RegistrationReason.USERNAME_LENGTH)
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise RegistrationError(RegistrationReason.PASSWORD_LENGTH)
