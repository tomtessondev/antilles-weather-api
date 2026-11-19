"""The batch project's export contract (`dashboard/src/lib/schema.ts` there), in Pydantic:
a file that does not match fails before anything is written."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict


class _Row(BaseModel):
    # Unknown fields are ignored, as the dashboard's zod schema does: the export may grow.
    model_config = ConfigDict(extra="ignore", frozen=True)


class Location(_Row):
    location_code: str
    town: str
    territory: Literal["Guadeloupe", "Martinique"]
    latitude: float
    longitude: float


class DailyWeather(_Row):
    location_code: str
    observed_date: date
    temp_min_c: float | None
    temp_max_c: float | None
    temp_avg_c: float | None
    rain_total_mm: float
    wind_max_kmh: float | None
    hours_observed: int


class DailyAirQuality(_Row):
    location_code: str
    observed_date: date
    pm10_avg_ugm3: float | None
    pm10_max_ugm3: float | None
    pm2_5_avg_ugm3: float | None
    dust_max_ugm3: float | None
    ozone_max_ugm3: float | None
    european_aqi_max: int | None
    exceeds_pm10_daily_limit: bool
    hours_observed: int


class Marts(_Row):
    generated_at: AwareDatetime
    locations: list[Location]
    weather: list[DailyWeather]
    air_quality: list[DailyAirQuality]
