"""A real PostgreSQL for the tests: the local Docker one (`make db`) or the CI service.
Migrations run once per session; every test that uses `db` starts from empty tables."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5435/weather_api_test"
)
ROOT = Path(__file__).resolve().parents[1]
TABLES = ("daily_weather", "daily_air_quality", "locations", "loads", "api_keys")


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(config, "head")
    engine = create_engine(TEST_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Engine:
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
    return engine


class FakeClock:
    """A monotonic clock the tests move by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def queries(db: Engine) -> Iterator[list[str]]:
    """Every SQL statement sent while the test runs."""
    from sqlalchemy import event

    sent: list[str] = []

    def record(*args: object) -> None:
        sent.append(str(args[2]))

    event.listen(db, "before_cursor_execute", record)
    yield sent
    event.remove(db, "before_cursor_execute", record)
