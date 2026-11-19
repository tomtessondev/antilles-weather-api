"""The tables, as SQLAlchemy Core: the loader writes them, the API reads them. Migrations
in `migrations/` create them; keep both in step."""

from __future__ import annotations

from functools import cache

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Engine,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
)

metadata = MetaData()

locations = Table(
    "locations",
    metadata,
    Column("location_code", String(8), primary_key=True),
    Column("town", String, nullable=False),
    Column("territory", String, nullable=False),
    Column("latitude", Float, nullable=False),
    Column("longitude", Float, nullable=False),
)


def _daily(name: str, *measures: Column[object]) -> Table:
    return Table(
        name,
        metadata,
        Column("location_code", String(8), ForeignKey("locations.location_code"), primary_key=True),
        Column("observed_date", Date, primary_key=True),
        *measures,
        Column("hours_observed", Integer, nullable=False),
        Index(f"ix_{name}_date_location", "observed_date", "location_code"),
    )


daily_weather = _daily(
    "daily_weather",
    Column("temp_min_c", Float),
    Column("temp_max_c", Float),
    Column("temp_avg_c", Float),
    Column("rain_total_mm", Float, nullable=False),
    Column("wind_max_kmh", Float),
)

daily_air_quality = _daily(
    "daily_air_quality",
    Column("pm10_avg_ugm3", Float),
    Column("pm10_max_ugm3", Float),
    Column("pm2_5_avg_ugm3", Float),
    Column("dust_max_ugm3", Float),
    Column("ozone_max_ugm3", Float),
    Column("european_aqi_max", Integer),
    Column("exceeds_pm10_daily_limit", Boolean, nullable=False),
)

loads = Table(
    "loads",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("generated_at", DateTime(timezone=True), nullable=False, unique=True),
    Column("loaded_at", DateTime(timezone=True), nullable=False),
    Column("locations", Integer, nullable=False),
    Column("weather_rows", Integer, nullable=False),
    Column("air_quality_rows", Integer, nullable=False),
)

api_keys = Table(
    "api_keys",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String, nullable=False, unique=True),
    Column("key_hash", String(64), nullable=False, unique=True),
    Column("per_minute", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
)


@cache
def engine_for(url: str) -> Engine:
    # Neon suspends idle computes: check connections before use instead of failing once.
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=0)
