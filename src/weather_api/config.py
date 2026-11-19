"""Settings, from the environment (and a local `.env` when present)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

MARTS_URL = "https://raw.githubusercontent.com/tomtessondev/antilles-data-pipeline/data/marts.json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5435/weather_api"
    marts_url: str = MARTS_URL
    # How often the response cache asks the database whether new data was loaded.
    cache_check_seconds: int = 60


def get_settings() -> Settings:
    return Settings()
