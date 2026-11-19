"""Identical requests are answered from memory until new data is loaded."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from tests.conftest import FakeClock
from weather_api.app import create_app
from weather_api.config import Settings
from weather_api.keys import create_key
from weather_api.load import load_marts
from weather_api.marts import Marts

RAW = json.loads((Path(__file__).parent / "fixtures" / "marts.json").read_text())


def test_cache_serves_without_the_database_until_new_data(
    db: Engine, clock: FakeClock, queries: list[str]
) -> None:
    load_marts(db, Marts.model_validate(RAW))
    key = {"X-API-Key": create_key(db, "test", per_minute=1000)}
    api = TestClient(create_app(Settings(), engine=db, clock=clock))
    first = api.get("/v1/weather", params={"location": "BTE"}, headers=key).json()
    queries.clear()
    assert api.get("/v1/weather", params={"location": "BTE"}, headers=key).json() == first
    assert queries == []

    newer = json.loads(json.dumps(RAW))
    newer["generated_at"] = "2026-11-05T10:12:00+00:00"
    newer["weather"][0]["rain_total_mm"] = 9.5
    load_marts(db, Marts.model_validate(newer))
    clock.advance(901)
    fresh = api.get("/v1/weather", params={"location": "BTE"}, headers=key).json()
    assert fresh["items"][0]["rain_total_mm"] == 9.5
