"""The SQL behind the data routes. Complete days only: a row counts when its
`hours_observed` is 24."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import ColumnElement, Engine, Table, and_, func, select, tuple_

from weather_api.db import daily_air_quality, daily_weather

COMPLETE = 24


def page(
    engine: Engine,
    table: Table,
    codes: list[str],
    start: date | None,
    end: date | None,
    after: tuple[date, str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Up to `limit + 1` complete rows after `after`, ordered by (date, town): the extra
    row tells the caller whether there is a next page."""
    conditions = [table.c.hours_observed == COMPLETE]
    if codes:
        conditions.append(table.c.location_code.in_(codes))
    if start:
        conditions.append(table.c.observed_date >= start)
    if end:
        conditions.append(table.c.observed_date <= end)
    if after:
        conditions.append(tuple_(table.c.observed_date, table.c.location_code) > tuple_(*after))
    statement = (
        select(*(c for c in table.columns if c.name != "hours_observed"))
        .where(and_(*conditions))
        .order_by(table.c.observed_date, table.c.location_code)
        .limit(limit + 1)
    )
    with engine.connect() as conn:
        return [dict(row._mapping) for row in conn.execute(statement)]


def latest_complete_day(engine: Engine, code: str) -> date | None:
    with engine.connect() as conn:
        value: date | None = conn.execute(
            select(func.max(daily_weather.c.observed_date)).where(
                daily_weather.c.location_code == code,
                daily_weather.c.hours_observed == COMPLETE,
            )
        ).scalar()
    return value


def period_figures(engine: Engine, code: str, start: date, end: date) -> dict[str, Any] | None:
    """Mean temperature, rain total, mean PM10, dust peak and days above the EU limit over
    the complete days of [start, end]; None when the period has no complete day."""

    def in_period(t: Table) -> ColumnElement[bool]:
        return and_(
            t.c.location_code == code,
            t.c.observed_date.between(start, end),
            t.c.hours_observed == COMPLETE,
        )

    with engine.connect() as conn:
        weather = conn.execute(
            select(
                func.count(),
                func.avg(daily_weather.c.temp_avg_c),
                func.sum(daily_weather.c.rain_total_mm),
            ).where(in_period(daily_weather))
        ).one()
        air = conn.execute(
            select(
                func.avg(daily_air_quality.c.pm10_avg_ugm3),
                func.count().filter(daily_air_quality.c.exceeds_pm10_daily_limit),
            ).where(in_period(daily_air_quality))
        ).one()
        peak = conn.execute(
            select(daily_air_quality.c.dust_max_ugm3, daily_air_quality.c.observed_date)
            .where(in_period(daily_air_quality), daily_air_quality.c.dust_max_ugm3.is_not(None))
            .order_by(daily_air_quality.c.dust_max_ugm3.desc(), daily_air_quality.c.observed_date)
            .limit(1)
        ).first()
    if weather[0] == 0:
        return None
    return {
        "start": start,
        "complete_days": weather[0],
        "end": end,
        "temp_avg_c": _round(weather[1]),
        "rain_total_mm": _round(weather[2]),
        "pm10_avg_ugm3": _round(air[0]),
        "dust_peak": {"value": peak[0], "date": peak[1]} if peak else None,
        "days_above_pm10_limit": air[1],
    }


def summary(engine: Engine, code: str, days: int) -> dict[str, Any] | None:
    end = latest_complete_day(engine, code)
    if end is None:
        return None
    start = end - timedelta(days=days - 1)
    current = period_figures(engine, code, start, end)
    if current is None:
        return None
    previous = period_figures(engine, code, start - timedelta(days=days), start - timedelta(days=1))
    return {"days": days, **current, "previous": previous}


def dust_episodes(
    engine: Engine, codes: list[str], start: date | None, end: date | None
) -> list[dict[str, Any]]:
    t = daily_air_quality
    # The export decides what is above the EU limit (its own flag), not the API.
    conditions = [t.c.hours_observed == COMPLETE, t.c.exceeds_pm10_daily_limit]
    if codes:
        conditions.append(t.c.location_code.in_(codes))
    if start:
        conditions.append(t.c.observed_date >= start)
    if end:
        conditions.append(t.c.observed_date <= end)
    statement = (
        select(t.c.location_code, t.c.observed_date, t.c.pm10_avg_ugm3, t.c.dust_max_ugm3)
        .where(and_(*conditions))
        .order_by(t.c.observed_date, t.c.location_code)
    )
    with engine.connect() as conn:
        return [dict(row._mapping) for row in conn.execute(statement)]


def _round(value: Any) -> float | None:
    return None if value is None else round(float(value), 2)
