"""Database engine과 request-scoped session lifecycle을 실제 SQLite로 검증한다."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

import app.core.database as database_module


class TrackingSession(Session):
    """실제 Session의 정리 호출만 기록한다."""

    def __init__(self, *, bind: Engine) -> None:
        super().__init__(bind=bind)
        self.close_calls = 0
        self.rollback_calls = 0

    def close(self) -> None:
        self.close_calls += 1
        super().close()

    def rollback(self) -> None:
        self.rollback_calls += 1
        super().rollback()


def test_create_database_engine_enforces_sqlite_foreign_keys() -> None:
    engine = database_module.create_database_engine("sqlite://")
    try:
        with engine.connect() as connection:
            foreign_keys_enabled = connection.scalar(text("PRAGMA foreign_keys"))
    finally:
        engine.dispose()

    assert foreign_keys_enabled == 1


def test_get_db_closes_the_request_session_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    session = TrackingSession(bind=engine)
    monkeypatch.setattr(database_module, "SessionLocal", lambda: session)

    dependency = database_module.get_db()

    assert next(dependency) is session
    dependency.close()

    assert session.rollback_calls == 0
    assert session.close_calls == 1
    engine.dispose()


def test_get_db_rolls_back_and_closes_the_request_session_after_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    session = TrackingSession(bind=engine)
    monkeypatch.setattr(database_module, "SessionLocal", lambda: session)
    dependency = database_module.get_db()

    next(dependency)
    with pytest.raises(RuntimeError, match="request failure"):
        dependency.throw(RuntimeError("request failure"))

    assert session.rollback_calls == 1
    assert session.close_calls == 1
    engine.dispose()


def test_init_db_creates_nested_sqlite_file_and_registered_tables(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "nested" / "chatbot.db"
    database_url = f"sqlite:///{database_path}"
    engine = create_engine(database_url)
    monkeypatch.setattr(database_module, "engine", engine)
    monkeypatch.setattr(database_module, "_database_url", make_url(database_url))

    try:
        database_module.init_db()
        table_names = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert database_path.is_file()
    assert {"users", "chat_exchanges"} <= table_names
