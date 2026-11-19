"""Weather, air quality, summaries and dust episodes: complete days only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from tests.conftest import FakeClock
from weather_api.app import create_app
from weather_api.config import Settings
from weather_api.keys import create_key
from weather_api.load import load_marts
from weather_api.marts import Marts

RAW = json.loads((Path(__file__).parent / "fixtures" / "marts.json").read_text())


@pytest.fixture
def api(db: Engine, clock: FakeClock) -> tuple[TestClient, dict[str, str]]:
    load_marts(db, Marts.model_validate(RAW))
    key = {"X-API-Key": create_key(db, "test", per_minute=1000)}
    return TestClient(create_app(Settings(), engine=db, clock=clock)), key


def get(api: tuple[TestClient, dict[str, str]], path: str, **params: Any) -> Any:
    client, key = api
    return client.get(path, params=params, headers=key)


def test_partial_days_are_never_served(api: tuple[TestClient, dict[str, str]]) -> None:
    for path in ("/v1/weather", "/v1/air-quality"):
        dates = {row["observed_date"] for row in get(api, path).json()["items"]}
        assert dates == {"2026-11-01", "2026-11-02"}
    summary = get(api, "/v1/locations/BTE/summary", days=7).json()
    assert summary["end"] == "2026-11-02"


def test_pagination_walks_every_row_once(api: tuple[TestClient, dict[str, str]]) -> None:
    seen: list[tuple[str, str]] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"limit": 1}
        if cursor:
            params["cursor"] = cursor
        page = get(api, "/v1/weather", **params).json()
        seen += [(r["observed_date"], r["location_code"]) for r in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == sorted(seen) and len(seen) == len(set(seen)) == 4


def test_filters_by_town_and_dates(api: tuple[TestClient, dict[str, str]]) -> None:
    rows = get(api, "/v1/weather", location="FDF", start="2026-11-02").json()["items"]
    assert [(r["location_code"], r["observed_date"]) for r in rows] == [("FDF", "2026-11-02")]
    assert get(api, "/v1/weather", start="2026-11-02", end="2026-11-01").status_code == 422


def test_garbled_cursor_is_422(api: tuple[TestClient, dict[str, str]]) -> None:
    for cursor in ("not base64!", "bm90IGEgY3Vyc29y"):
        response = get(api, "/v1/air-quality", cursor=cursor)
        assert response.status_code == 422
        assert response.headers["content-type"].startswith("application/problem+json")


def test_unknown_town_in_filter_is_404(api: tuple[TestClient, dict[str, str]]) -> None:
    assert get(api, "/v1/weather", location="XXX").status_code == 404
    assert get(api, "/v1/locations/XXX/summary", days=7).status_code == 404


def test_summary_values(api: tuple[TestClient, dict[str, str]]) -> None:
    summary = get(api, "/v1/locations/BTE/summary", days=7).json()
    assert (summary["start"], summary["end"]) == ("2026-10-27", "2026-11-02")
    assert summary["temp_avg_c"] == 26.5
    assert summary["rain_total_mm"] == 4.0
    assert summary["pm10_avg_ugm3"] == 41.0
    assert summary["dust_peak"] == {"value": 210.0, "date": "2026-11-02"}
    assert summary["days_above_pm10_limit"] == 1
    assert summary["previous"] is None
    assert get(api, "/v1/locations/BTE/summary", days=10).status_code == 422


def test_dust_episodes_list_days_above_the_limit(api: tuple[TestClient, dict[str, str]]) -> None:
    items = get(api, "/v1/dust-episodes").json()["items"]
    assert items == [
        {
            "location_code": "BTE",
            "observed_date": "2026-11-02",
            "pm10_avg_ugm3": 62.0,
            "dust_max_ugm3": 210.0,
        }
    ]


def test_empty_database_is_503_for_data_routes(db: Engine, clock: FakeClock) -> None:
    key = {"X-API-Key": create_key(db, "test", per_minute=1000)}
    client = TestClient(create_app(Settings(), engine=db, clock=clock))
    for path in ("/v1/weather", "/v1/air-quality", "/v1/dust-episodes", "/v1/locations"):
        response = client.get(path, headers=key)
        assert response.status_code == 503, path
        assert "no data" in response.json()["detail"].lower()


def test_unknown_parameters_do_not_grow_the_cache(
    api: tuple[TestClient, dict[str, str]],
) -> None:
    client, _ = api
    for i in range(30):
        get(api, "/v1/weather", junk=str(i))
    assert len(client.app.state.response_cache) == 1  # type: ignore[attr-defined]  # Starlette app


def test_keyed_answers_are_cached_privately(api: tuple[TestClient, dict[str, str]]) -> None:
    """Behind a key, a shared cache must not hand the answer to callers without one."""
    assert get(api, "/v1/weather").headers["Cache-Control"] == "private, max-age=300"


def test_episodes_and_limit_days_follow_the_export_flag(db: Engine, clock: FakeClock) -> None:
    """The export decides what counts as above the EU limit; the API does not redefine it."""
    flagged = json.loads(json.dumps(RAW))
    flagged["air_quality"][1]["exceeds_pm10_daily_limit"] = False  # BTE 2026-11-02, PM10 62
    flagged["air_quality"][4]["exceeds_pm10_daily_limit"] = True  # FDF 2026-11-02, PM10 40
    load_marts(db, Marts.model_validate(flagged))
    key = {"X-API-Key": create_key(db, "test", per_minute=1000)}
    client = TestClient(create_app(Settings(), engine=db, clock=clock))
    items = client.get("/v1/dust-episodes", headers=key).json()["items"]
    assert [(i["location_code"], i["observed_date"]) for i in items] == [("FDF", "2026-11-02")]
    summary = client.get("/v1/locations/BTE/summary", headers=key).json()
    assert summary["days_above_pm10_limit"] == 0


def test_summary_says_how_many_complete_days_it_covers(
    api: tuple[TestClient, dict[str, str]],
) -> None:
    assert get(api, "/v1/locations/BTE/summary", days=7).json()["complete_days"] == 2
