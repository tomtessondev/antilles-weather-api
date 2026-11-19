"""Health, metadata and towns."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine

from tests.conftest import FakeClock
from weather_api.app import create_app
from weather_api.config import Settings
from weather_api.keys import create_key
from weather_api.load import load_marts
from weather_api.marts import Marts

RAW = json.loads((Path(__file__).parent / "fixtures" / "marts.json").read_text())


def test_health_reports_the_database(db: Engine, clock: FakeClock) -> None:
    assert TestClient(create_app(Settings(), engine=db, clock=clock)).get("/health").json() == {
        "status": "ok"
    }
    down = create_engine(
        "postgresql+psycopg://x:y@127.0.0.1:1/none", connect_args={"connect_timeout": 1}
    )
    response = TestClient(create_app(Settings(), engine=down, clock=clock)).get("/health")
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")


def test_no_data_loaded_yet_is_503(db: Engine, clock: FakeClock) -> None:
    api = TestClient(create_app(Settings(), engine=db, clock=clock))
    key = {"X-API-Key": create_key(db, "demo", per_minute=60)}
    response = api.get("/v1/meta", headers=key)
    assert response.status_code == 503
    assert "no data" in response.json()["detail"].lower()


def test_meta_and_locations(db: Engine, clock: FakeClock) -> None:
    load_marts(db, Marts.model_validate(RAW))
    api = TestClient(create_app(Settings(), engine=db, clock=clock))
    key = {"X-API-Key": create_key(db, "demo", per_minute=60)}
    assert api.get("/v1/meta", headers=key).json()["generated_at"].startswith("2026-11-04T10:12")
    towns = api.get("/v1/locations", headers=key).json()
    assert [t["location_code"] for t in towns] == ["BTE", "FDF"]
    assert set(towns[0]) == {"location_code", "town", "territory", "latitude", "longitude"}
    assert api.get("/v1/locations/FDF", headers=key).json()["town"] == "Fort-de-France"
    missing = api.get("/v1/locations/XXX", headers=key)
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/problem+json")
