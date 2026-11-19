"""Responses kept in memory until the data changes. The data changes once a day, so the
cache asks the database for the latest load at most every `check_seconds`; in between,
identical requests never reach it (Neon can stay asleep)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from weather_api.access import Clock


class ResponseCache:
    def __init__(
        self, clock: Clock, check_seconds: float, latest: Callable[[], datetime | None]
    ) -> None:
        self._clock, self._check_seconds, self._latest = clock, check_seconds, latest
        self._checked_at: float | None = None
        self._version: datetime | None = None
        self._entries: dict[str, Any] = {}

    def _refresh(self) -> None:
        now = self._clock()
        if self._checked_at is not None and now - self._checked_at < self._check_seconds:
            return
        version = self._latest()
        if version != self._version:
            self._entries.clear()
            self._version = version
        self._checked_at = now

    def get_or_compute(self, key: str, compute: Callable[[], Any]) -> Any:
        self._refresh()
        if key not in self._entries:
            self._entries[key] = compute()
        return self._entries[key]
