"""Weather, air quality, town summaries and dust episodes. Complete days only; answers are
cached in memory until new data is loaded."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import Table

from weather_api import queries
from weather_api.access import require_key
from weather_api.cache import ResponseCache
from weather_api.db import daily_air_quality, daily_weather

router = APIRouter(prefix="/v1", dependencies=[Depends(require_key)])
CACHE_CONTROL = "public, max-age=300"


class DailyWeather(BaseModel):
    location_code: str
    observed_date: date
    temp_min_c: float | None
    temp_max_c: float | None
    temp_avg_c: float | None
    rain_total_mm: float
    wind_max_kmh: float | None


class DailyAirQuality(BaseModel):
    location_code: str
    observed_date: date
    pm10_avg_ugm3: float | None
    pm10_max_ugm3: float | None
    pm2_5_avg_ugm3: float | None
    dust_max_ugm3: float | None
    ozone_max_ugm3: float | None
    european_aqi_max: int | None
    exceeds_pm10_daily_limit: bool


class WeatherPage(BaseModel):
    items: list[DailyWeather]
    next_cursor: str | None


class AirQualityPage(BaseModel):
    items: list[DailyAirQuality]
    next_cursor: str | None


class DustPeak(BaseModel):
    value: float
    date: date


class PeriodFigures(BaseModel):
    start: date
    end: date
    temp_avg_c: float | None
    rain_total_mm: float | None
    pm10_avg_ugm3: float | None
    dust_peak: DustPeak | None
    days_above_pm10_limit: int


class Summary(PeriodFigures):
    days: Literal[7, 14, 30]
    previous: PeriodFigures | None


class DustEpisode(BaseModel):
    location_code: str
    observed_date: date
    pm10_avg_ugm3: float
    dust_max_ugm3: float | None


class DustEpisodes(BaseModel):
    items: list[DustEpisode]


Towns = Annotated[list[str], Query(alias="location", description="Town codes, repeatable")]
Start = Annotated[date | None, Query(description="First day, inclusive (ISO date)")]
End = Annotated[date | None, Query(description="Last day, inclusive (ISO date)")]
Limit = Annotated[int, Query(ge=1, le=500, description="Rows per page")]
Cursor = Annotated[str | None, Query(description="The `next_cursor` of the previous page")]


def encode_cursor(day: date, code: str) -> str:
    return base64.urlsafe_b64encode(f"{day.isoformat()}|{code}".encode()).decode()


def decode_cursor(cursor: str) -> tuple[date, str]:
    try:
        day, code = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return date.fromisoformat(day), code
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise HTTPException(422, "cursor: not a cursor returned by this API") from error


def _cached[T](request: Request, response: Response, compute: Callable[[], T]) -> T:
    cache: ResponseCache = request.app.state.response_cache
    key = f"{request.url.path}?{sorted(request.query_params.multi_items())}"
    response.headers["Cache-Control"] = CACHE_CONTROL
    result: T = cache.get_or_compute(key, compute)
    return result


def _check(request: Request, codes: list[str], start: date | None, end: date | None) -> None:
    if start and end and start > end:
        raise HTTPException(422, "start: must not be after end")
    unknown = queries.unknown_codes(request.app.state.engine, codes)
    if unknown:
        raise HTTPException(404, f"No town with code {', '.join(map(repr, unknown))}.")


def _page(
    request: Request, table: Table, codes: list[str], start: date | None, end: date | None,
    cursor: str | None, limit: int,
) -> dict[str, Any]:  # fmt: skip
    after = decode_cursor(cursor) if cursor else None
    _check(request, codes, start, end)
    rows = queries.page(request.app.state.engine, table, codes, start, end, after, limit)
    more = len(rows) > limit
    rows = rows[:limit]
    last = rows[-1] if rows else None
    next_cursor = (
        encode_cursor(last["observed_date"], last["location_code"]) if more and last else None
    )
    return {"items": rows, "next_cursor": next_cursor}


@router.get("/weather", tags=["daily"], summary="Daily weather per town")
def weather(
    request: Request, response: Response, location: Towns = [], start: Start = None,  # noqa: B006
    end: End = None, limit: Limit = 100, cursor: Cursor = None,
) -> WeatherPage:  # fmt: skip
    page = _cached(
        request, response,
        lambda: _page(request, daily_weather, location, start, end, cursor, limit),
    )  # fmt: skip
    return WeatherPage.model_validate(page)


@router.get("/air-quality", tags=["daily"], summary="Daily air quality per town")
def air_quality(
    request: Request, response: Response, location: Towns = [], start: Start = None,  # noqa: B006
    end: End = None, limit: Limit = 100, cursor: Cursor = None,
) -> AirQualityPage:  # fmt: skip
    page = _cached(
        request, response,
        lambda: _page(request, daily_air_quality, location, start, end, cursor, limit),
    )  # fmt: skip
    return AirQualityPage.model_validate(page)


@router.get(
    "/locations/{code}/summary",
    tags=["towns"],
    summary="A town's latest complete days, against the days before",
)
def summary(
    request: Request, response: Response, code: str,
    days: Annotated[int, Query(description="Length of the period: 7, 14 or 30 days")] = 7,
) -> Summary:  # fmt: skip
    if days not in (7, 14, 30):
        raise HTTPException(422, "days: must be 7, 14 or 30")

    def compute() -> dict[str, Any]:
        _check(request, [code], None, None)
        figures = queries.summary(request.app.state.engine, code, days)
        if figures is None:
            raise HTTPException(404, f"No complete day for {code!r} yet.")
        return figures

    return Summary.model_validate(_cached(request, response, compute))


@router.get(
    "/dust-episodes",
    tags=["daily"],
    summary="Days whose PM10 daily mean is above the EU limit (50 µg/m³)",
)
def dust_episodes(
    request: Request, response: Response, location: Towns = [],  # noqa: B006
    start: Start = None, end: End = None,
) -> DustEpisodes:  # fmt: skip
    def compute() -> dict[str, Any]:
        _check(request, location, start, end)
        return {"items": queries.dust_episodes(request.app.state.engine, location, start, end)}

    return DustEpisodes.model_validate(_cached(request, response, compute))
