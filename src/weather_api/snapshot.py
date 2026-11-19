"""What every request needs from the database, held in memory: the active keys, the town
codes and the latest load. It is read in one go at most every `refresh_seconds` (15 min by
default), so callers (even guessing keys or polling /health) do not keep Neon awake. The
cost: a revoked key keeps working, and new data shows up, up to one refresh later."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import Engine, select

from weather_api.db import api_keys, loads, locations
from weather_api.keys import KeyInfo

Clock = Callable[[], float]


@dataclass(frozen=True)
class State:
    generated_at: datetime | None
    loaded_at: datetime | None
    keys: dict[str, KeyInfo] = field(default_factory=dict)  # active keys by hash
    codes: frozenset[str] = frozenset()


class Snapshot:
    def __init__(self, engine: Engine, clock: Clock, refresh_seconds: float) -> None:
        self._engine, self._clock, self._refresh = engine, clock, refresh_seconds
        self._state: State | None = None
        self._read_at = 0.0
        self._lock = threading.Lock()

    def get(self) -> State:
        with self._lock:
            if self._state is None or self._clock() - self._read_at >= self._refresh:
                self._state = self._read()
                self._read_at = self._clock()
            return self._state

    def _read(self) -> State:
        with self._engine.connect() as conn:
            latest = conn.execute(
                select(loads.c.generated_at, loads.c.loaded_at)
                .order_by(loads.c.generated_at.desc())
                .limit(1)
            ).first()
            active = conn.execute(
                select(
                    api_keys.c.key_hash, api_keys.c.name, api_keys.c.per_minute,
                    api_keys.c.created_at, api_keys.c.revoked_at,
                ).where(api_keys.c.revoked_at.is_(None))
            )  # fmt: skip
            keys = {row[0]: KeyInfo(*row[1:]) for row in active}
            codes = frozenset(conn.execute(select(locations.c.location_code)).scalars())
        return State(
            generated_at=latest[0] if latest else None,
            loaded_at=latest[1] if latest else None,
            keys=keys,
            codes=codes,
        )
