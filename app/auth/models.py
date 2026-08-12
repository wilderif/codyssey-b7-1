"""Auth domain의 SQLAlchemy model이다."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_types import UTCDateTime, utc_now

USER_ROLE = "user"
ADMIN_ROLE = "admin"


class User(Base):
    """회원가입과 login에 사용하는 사용자 계정이다."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=USER_ROLE,
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
    )
