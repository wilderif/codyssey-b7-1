"""pytest fixtures shared by application tests."""

from __future__ import annotations

from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.models import User
from app.chat.models import ChatExchange  # noqa: F401
from app.core.database import Base


@pytest.fixture
def isolated_env_file_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Repository의 .env와 격리된 작업 directory를 제공한다."""

    monkeypatch.chdir(tmp_path)


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
def user_id_factory(db: Session) -> Callable[[str], int]:
    """Username으로 test User를 만들고 ID를 반환하는 factory를 제공한다."""

    def create_test_user(username: str) -> int:
        user = User(username=username, password_hash="test-hash")
        db.add(user)
        db.flush()
        return user.id

    return create_test_user


@pytest.fixture
def user_id(db: Session, user_id_factory: Callable[[str], int]) -> int:
    """test용 login 사용자 ID를 반환한다."""

    created_user_id = user_id_factory("test-user")
    db.commit()
    return created_user_id
