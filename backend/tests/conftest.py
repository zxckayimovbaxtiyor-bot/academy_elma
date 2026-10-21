"""Tests run against a real PostgreSQL 16 database whose name must end in ``_test``.

    TEST_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/academy_test pytest

The schema is rebuilt from the Alembic migrations once per session (which tests
the migrations too). Each test runs in a transaction that is rolled back.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

TEST_URL = os.environ.get("TEST_DATABASE_URL", "")
if not TEST_URL:
    pytest.exit("Set TEST_DATABASE_URL to a PostgreSQL database named *_test", returncode=2)

# Settings are read at import time: point everything at the test database and keep
# password hashing cheap so the suite stays fast.
os.environ["DATABASE_URL"] = TEST_URL
os.environ["ARGON2_TIME_COST"] = "1"
os.environ["ARGON2_MEMORY_KIB"] = "1024"
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from alembic import command  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _ensure_database(url) -> None:
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def engine():
    url = make_url(TEST_URL)
    if not (url.database or "").endswith("_test"):
        pytest.exit("Refusing to run: the test database name must end in _test", returncode=2)
    _ensure_database(url)
    eng = create_engine(url)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["url"] = TEST_URL
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    conn = engine.connect()
    trans = conn.begin()
    session = Session(
        bind=conn,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    yield session
    session.close()
    trans.rollback()
    conn.close()


def _make_client(db, csrf: bool = True) -> TestClient:
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    headers = {"X-Requested-With": "pytest"} if csrf else {}
    return TestClient(app, headers=headers)


@pytest.fixture
def client(db):
    from app.main import app

    with _make_client(db) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def make_client(db):
    """Extra independent browsers (each with its own cookie jar)."""
    from app.main import app

    clients: list[TestClient] = []

    def factory(csrf: bool = True) -> TestClient:
        c = _make_client(db, csrf)
        c.__enter__()
        clients.append(c)
        return c

    yield factory
    for c in clients:
        c.__exit__(None, None, None)
    app.dependency_overrides.clear()


class FrozenClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock(monkeypatch) -> FrozenClock:
    frozen = FrozenClock(datetime(2026, 10, 19, 9, 0, tzinfo=UTC))
    monkeypatch.setattr("app.clock.utcnow", lambda: frozen.now)
    return frozen


@pytest.fixture(autouse=True)
def media_root(tmp_path, monkeypatch) -> Path:
    """Every test writes media into its own temporary folder."""
    root = tmp_path / "media"
    root.mkdir()
    monkeypatch.setattr("app.config.settings.media_root", str(root))
    return root


@pytest.fixture
def reference(db):
    """Reference data plus two branches (Tashkent city, Samarkand)."""
    from app.cli import seed_reference
    from tests.factories import Reference

    seed_reference(db)
    return Reference.load(db)
