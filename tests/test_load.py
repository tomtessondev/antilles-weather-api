"""Loading the batch marts: idempotent, the file is the full state, all or nothing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from pydantic import ValidationError
from sqlalchemy import Engine, func, select

from weather_api.config import MARTS_URL
from weather_api.db import daily_air_quality, daily_weather, loads, locations
from weather_api.load import fetch_marts, load_marts
from weather_api.marts import Marts

RAW: dict[str, Any] = json.loads((Path(__file__).parent / "fixtures" / "marts.json").read_text())


def count(db: Engine, table: Any) -> int:
    with db.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(table)).scalar_one())


def test_load_inserts_every_row(db: Engine) -> None:
    result = load_marts(db, Marts.model_validate(RAW))
    assert (result.skipped, result.locations, result.weather_rows) == (False, 2, 6)
    assert (count(db, locations), count(db, daily_weather), count(db, daily_air_quality)) == (
        2,
        6,
        6,
    )
    assert count(db, loads) == 1


def test_same_file_twice_is_skipped(db: Engine) -> None:
    load_marts(db, Marts.model_validate(RAW))
    assert load_marts(db, Marts.model_validate(RAW)).skipped is True
    assert (count(db, daily_weather), count(db, loads)) == (6, 1)


def test_newer_file_updates_and_deletes_vanished_rows(db: Engine) -> None:
    load_marts(db, Marts.model_validate(RAW))
    newer = json.loads(json.dumps(RAW))
    newer["generated_at"] = "2026-11-05T10:12:00+00:00"
    newer["weather"][0]["rain_total_mm"] = 9.5
    del newer["weather"][-1]
    load_marts(db, Marts.model_validate(newer))
    with db.connect() as conn:
        rain = conn.execute(
            select(daily_weather.c.rain_total_mm).where(daily_weather.c.location_code == "BTE")
            .order_by(daily_weather.c.observed_date).limit(1)
        ).scalar_one()  # fmt: skip
    assert rain == 9.5
    assert count(db, daily_weather) == 5


def test_invalid_file_writes_nothing(db: Engine) -> None:
    broken = json.loads(json.dumps(RAW))
    broken["locations"][0]["territory"] = "Cuba"
    with pytest.raises(ValidationError):
        load_marts(db, Marts.model_validate(broken))
    assert count(db, locations) == 0


@respx.mock
def test_fetch_reads_the_published_file() -> None:
    respx.get(MARTS_URL).mock(return_value=httpx.Response(200, json=RAW))
    with httpx.Client() as client:
        marts = fetch_marts(client, MARTS_URL)
    assert [loc.location_code for loc in marts.locations] == ["BTE", "FDF"]


def test_a_town_removed_with_its_rows_is_deleted(db: Engine) -> None:
    load_marts(db, Marts.model_validate(RAW))
    newer = json.loads(json.dumps(RAW))
    newer["generated_at"] = "2026-11-05T10:12:00+00:00"
    newer["locations"] = [loc for loc in newer["locations"] if loc["location_code"] != "FDF"]
    for name in ("weather", "air_quality"):
        newer[name] = [r for r in newer[name] if r["location_code"] != "FDF"]
    load_marts(db, Marts.model_validate(newer))
    assert (count(db, locations), count(db, daily_weather), count(db, daily_air_quality)) == (
        1,
        3,
        3,
    )


def test_extra_fields_in_the_file_are_ignored(db: Engine) -> None:
    """The batch export may add columns (it has `last_extracted_at`); like the dashboard's
    zod schema, the loader keeps the fields it knows and ignores the others."""
    richer = json.loads(json.dumps(RAW))
    for row in richer["air_quality"]:
        row["last_extracted_at"] = "2026-11-04T10:00:00"
    assert load_marts(db, Marts.model_validate(richer)).air_quality_rows == 6


def test_an_older_file_is_skipped(db: Engine) -> None:
    """A stale copy (CDN cache, old commit) must not overwrite newer rows."""
    newer = json.loads(json.dumps(RAW))
    newer["generated_at"] = "2026-11-05T10:12:00+00:00"
    newer["weather"][0]["rain_total_mm"] = 9.5
    load_marts(db, Marts.model_validate(newer))
    assert load_marts(db, Marts.model_validate(RAW)).skipped is True
    with db.connect() as conn:
        rains = set(conn.execute(select(daily_weather.c.rain_total_mm)).scalars())
    assert 9.5 in rains


def test_an_empty_file_is_refused(db: Engine) -> None:
    empty = json.loads(json.dumps(RAW))
    empty["generated_at"] = "2026-11-05T10:12:00+00:00"
    empty["weather"] = []
    with pytest.raises(ValidationError):
        load_marts(db, Marts.model_validate(empty))
