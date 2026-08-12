"""Shared SQLAlchemy engine, metadata, and session lifecycle."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

SQLITE_BACKEND_NAME = "sqlite"


class Base(DeclarativeBase):
    """모든 application model이 공유하는 declarative base다."""


def _enable_sqlite_foreign_keys(
    dbapi_connection: Any,
    _connection_record: object,
) -> None:
    has_autocommit = hasattr(dbapi_connection, "autocommit")
    previous_autocommit = getattr(dbapi_connection, "autocommit", None)
    if has_autocommit:
        dbapi_connection.autocommit = True

    try:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
    finally:
        if has_autocommit:
            dbapi_connection.autocommit = previous_autocommit


def create_database_engine(database_url: str) -> Engine:
    """URL에 맞는 engine을 만들고 SQLite connection 계약을 적용한다."""

    parsed_url = make_url(database_url)
    connect_args = (
        {"check_same_thread": False}
        if parsed_url.get_backend_name() == SQLITE_BACKEND_NAME
        else {}
    )
    created_engine = create_engine(parsed_url, connect_args=connect_args)
    if parsed_url.get_backend_name() == SQLITE_BACKEND_NAME:
        event.listen(created_engine, "connect", _enable_sqlite_foreign_keys)
    return created_engine


_database_url = make_url(settings.database_url)
engine = create_database_engine(settings.database_url)
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """요청마다 DB session을 제공하고 종료 시 반드시 정리한다."""

    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """등록된 model의 table을 생성한다."""

    _ensure_sqlite_directory(_database_url)
    Base.metadata.create_all(bind=engine)


def _ensure_sqlite_directory(url: URL) -> None:
    if url.get_backend_name() != SQLITE_BACKEND_NAME or url.database in (
        None,
        "",
        ":memory:",
    ):
        return

    Path(url.database).expanduser().parent.mkdir(parents=True, exist_ok=True)
