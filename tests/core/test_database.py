"""SQLite database directory lifecycle을 검증한다."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

import app.core.database as database_module


def test_init_db_rejects_missing_sqlite_parent_when_creation_is_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production에서는 누락된 Volume 경로를 새로 만들면 안 된다."""

    database_path = tmp_path / "missing-volume" / "chatbot.db"
    database_url = make_url(f"sqlite:///{database_path}")
    test_engine = create_engine(database_url)
    monkeypatch.setattr(database_module, "_database_url", database_url)
    monkeypatch.setattr(database_module, "engine", test_engine)

    try:
        with pytest.raises(RuntimeError, match="DATABASE_URL parent directory"):
            database_module.init_db(create_sqlite_directory=False)
    finally:
        test_engine.dispose()

    assert not database_path.parent.exists()
