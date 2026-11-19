"""Alembic runs migrations online against DATABASE_URL, or the URL a caller set."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

from weather_api.config import get_settings

url = context.config.get_main_option("sqlalchemy.url") or get_settings().database_url

with create_engine(url).connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
