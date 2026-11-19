"""Settings come from the environment."""

from __future__ import annotations

import pytest

from weather_api.config import MARTS_URL, get_settings


def test_settings_read_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host:5432/db")
    settings = get_settings()
    assert settings.database_url == "postgresql+psycopg://u:p@host:5432/db"
    assert settings.marts_url == MARTS_URL
    assert settings.cache_check_seconds == 60


def test_neon_urls_are_accepted_as_given(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neon (and most hosts) hand out postgresql:// URLs; SQLAlchemy needs the driver."""
    for given in ("postgresql://u:p@ep-x.neon.tech/db?sslmode=require", "postgres://u:p@h/db"):
        monkeypatch.setenv("DATABASE_URL", given)
        assert get_settings().database_url.startswith("postgresql+psycopg://")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    assert get_settings().database_url == "postgresql+psycopg://u:p@h/db"
