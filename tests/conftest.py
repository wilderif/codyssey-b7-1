"""pytest fixtures shared by application tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.models import User
from app.chat.models import ChatExchange  # noqa: F401
from app.core.database import Base


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """격리된 SQLite DB session을 제공한다."""

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection: Any, _record: object) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def user_id(db: Session) -> int:
    """test용 login 사용자 ID를 반환한다."""

    user = User(username="test-user", password_hash="test-hash")
    db.add(user)
    db.flush()
    created_user_id = user.id
    db.commit()
    return created_user_id
