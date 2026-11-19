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
