"""Access control: keys, quotas, and a database left asleep by bad callers."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from tests.conftest import FakeClock
from weather_api.app import create_app
from weather_api.config import Settings
from weather_api.keys import create_key, revoke_key

PROBLEM = "application/problem+json"


def client(db: Engine, clock: FakeClock) -> TestClient:
    return TestClient(create_app(Settings(), engine=db, clock=clock))


def test_missing_unknown_and_revoked_keys_get_401_problem(db: Engine, clock: FakeClock) -> None:
    api = client(db, clock)
    revoked = create_key(db, "old", per_minute=60)
    revoke_key(db, "old")
    unknown = "aw_" + "x" * 43
    for headers in ({}, {"X-API-Key": unknown}, {"X-API-Key": revoked}):
        response = api.get("/v1/locations", headers=headers)
        assert response.status_code == 401
        assert response.headers["content-type"].startswith(PROBLEM)
        assert response.json()["status"] == 401


def test_malformed_key_is_rejected_without_a_query(
    db: Engine, clock: FakeClock, queries: list[str]
) -> None:
    api = client(db, clock)
    queries.clear()
    assert api.get("/v1/locations", headers={"X-API-Key": "not-a-key"}).status_code == 401
    assert queries == []


def test_quota_returns_429_with_retry_after(db: Engine, clock: FakeClock) -> None:
    api = client(db, clock)
    key = {"X-API-Key": create_key(db, "tight", per_minute=2)}
    first = api.get("/v1/locations", headers=key)
    assert (first.status_code, first.headers["RateLimit-Limit"]) == (200, "2")
    assert first.headers["RateLimit-Remaining"] == "1"
    api.get("/v1/locations", headers=key)
    third = api.get("/v1/locations", headers=key)
    assert third.status_code == 429
    assert int(third.headers["Retry-After"]) > 0 and third.headers["RateLimit-Remaining"] == "0"
    clock.advance(60)
    assert api.get("/v1/locations", headers=key).status_code == 200


def test_revoked_key_works_until_the_cache_expires(db: Engine, clock: FakeClock) -> None:
    api = client(db, clock)
    raw = create_key(db, "leaving", per_minute=60)
    key = {"X-API-Key": raw}
    assert api.get("/v1/locations", headers=key).status_code == 200
    revoke_key(db, "leaving")
    clock.advance(59)
    assert api.get("/v1/locations", headers=key).status_code == 200
    clock.advance(2)
    assert api.get("/v1/locations", headers=key).status_code == 401


def test_cors_allows_get_from_anywhere(db: Engine, clock: FakeClock) -> None:
    response = client(db, clock).options(
        "/v1/locations",
        headers={"Origin": "https://example.org", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers["access-control-allow-origin"] == "*"
