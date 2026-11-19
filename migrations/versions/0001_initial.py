"""Towns, daily weather and air quality, loads, API keys.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None


def _daily(name: str, *measures: sa.Column[object]) -> None:
    op.create_table(
        name,
        sa.Column("location_code", sa.String(8), sa.ForeignKey("locations.location_code")),
        sa.Column("observed_date", sa.Date),
        *measures,
        sa.Column("hours_observed", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint("location_code", "observed_date"),
    )
    op.create_index(f"ix_{name}_date_location", name, ["observed_date", "location_code"])


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("location_code", sa.String(8), primary_key=True),
        sa.Column("town", sa.String, nullable=False),
        sa.Column("territory", sa.String, nullable=False),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
    )
    _daily(
        "daily_weather",
        sa.Column("temp_min_c", sa.Float),
        sa.Column("temp_max_c", sa.Float),
        sa.Column("temp_avg_c", sa.Float),
        sa.Column("rain_total_mm", sa.Float, nullable=False),
        sa.Column("wind_max_kmh", sa.Float),
    )
    _daily(
        "daily_air_quality",
        sa.Column("pm10_avg_ugm3", sa.Float),
        sa.Column("pm10_max_ugm3", sa.Float),
        sa.Column("pm2_5_avg_ugm3", sa.Float),
        sa.Column("dust_max_ugm3", sa.Float),
        sa.Column("ozone_max_ugm3", sa.Float),
        sa.Column("european_aqi_max", sa.Integer),
        sa.Column("exceeds_pm10_daily_limit", sa.Boolean, nullable=False),
    )
    op.create_table(
        "loads",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, unique=True),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locations", sa.Integer, nullable=False),
        sa.Column("weather_rows", sa.Integer, nullable=False),
        sa.Column("air_quality_rows", sa.Integer, nullable=False),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False, unique=True),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("per_minute", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    for table in ("api_keys", "loads", "daily_air_quality", "daily_weather", "locations"):
        op.drop_table(table)
