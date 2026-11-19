"""Settings, from the environment (and a local `.env` when present)."""

from __future__ import annotations

import re

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MARTS_URL = "https://raw.githubusercontent.com/tomtessondev/antilles-data-pipeline/data/marts.json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5435/weather_api"
    marts_url: str = MARTS_URL
    # How often the response cache asks the database whether new data was loaded.
    cache_check_seconds: int = 60

    @field_validator("database_url")
    @classmethod
    def _with_driver(cls, url: str) -> str:
        """Neon hands out postgresql:// URLs; SQLAlchemy needs the driver named."""
        return re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", url)


def get_settings() -> Settings:
    return Settings()
