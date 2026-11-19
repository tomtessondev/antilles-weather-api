"""Copies `marts.json` into PostgreSQL. The file is the full state of the marts: rows are
upserted, rows it no longer holds are deleted, all in one transaction; a file already
loaded (same `generated_at`) is skipped."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import Connection, Engine, Table, delete, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert

from weather_api.db import daily_air_quality, daily_weather, loads, locations
from weather_api.marts import Marts

DAILY_KEYS = ["location_code", "observed_date"]
DELETE_BATCH = 1000


@dataclass(frozen=True)
class LoadResult:
    skipped: bool
    locations: int
    weather_rows: int
    air_quality_rows: int


def fetch_marts(client: httpx.Client, url: str) -> Marts:
    response = client.get(url, timeout=60, follow_redirects=True)
    response.raise_for_status()
    return Marts.model_validate_json(response.content)


def _upsert(conn: Connection, table: Table, rows: list[dict[str, Any]], keys: list[str]) -> None:
    """One statement run for every row (executemany): no parameter limit on large exports."""
    if not rows:
        return
    statement = insert(table)
    updates = {c.name: statement.excluded[c.name] for c in table.columns if c.name not in keys}
    conn.execute(statement.on_conflict_do_update(index_elements=keys, set_=updates), rows)


def _delete_missing(
    conn: Connection, table: Table, rows: list[dict[str, Any]], keys: list[str]
) -> None:
    """Delete the rows the file no longer holds, by key, a batch at a time."""
    columns = [table.c[k] for k in keys]
    present = {tuple(row[k] for k in keys) for row in rows}
    stored = {tuple(row) for row in conn.execute(select(*columns))}
    missing = sorted(stored - present)
    for i in range(0, len(missing), DELETE_BATCH):
        conn.execute(delete(table).where(tuple_(*columns).in_(missing[i : i + DELETE_BATCH])))


def load_marts(engine: Engine, marts: Marts) -> LoadResult:
    town_rows = [r.model_dump() for r in marts.locations]
    weather = [r.model_dump() for r in marts.weather]
    air = [r.model_dump() for r in marts.air_quality]
    with engine.begin() as conn:
        latest = conn.execute(select(func.max(loads.c.generated_at))).scalar()
        # The same file again, or an older copy (CDN cache, old commit): keep what is there.
        if latest is not None and marts.generated_at <= latest:
            return LoadResult(True, 0, 0, 0)
        # Towns first for the inserts, last for the deletes: daily rows reference them.
        _upsert(conn, locations, town_rows, ["location_code"])
        for table, rows in ((daily_weather, weather), (daily_air_quality, air)):
            _upsert(conn, table, rows, DAILY_KEYS)
            _delete_missing(conn, table, rows, DAILY_KEYS)
        _delete_missing(conn, locations, town_rows, ["location_code"])
        conn.execute(
            insert(loads).values(
                generated_at=marts.generated_at,
                loaded_at=datetime.now(UTC),
                locations=len(town_rows),
                weather_rows=len(weather),
                air_quality_rows=len(air),
            )
        )
    return LoadResult(False, len(town_rows), len(weather), len(air))
