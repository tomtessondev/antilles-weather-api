"""Answers kept in memory until the data changes (a new load), at most `max_entries` of
them, least recently used dropped first. Keys are built from validated parameters only, so
junk query strings cannot grow the cache."""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from datetime import datetime
from typing import Any


class ResponseCache:
    def __init__(self, max_entries: int = 512) -> None:
        self._max = max_entries
        self._version: datetime | None = None
        self._entries: OrderedDict[Hashable, Any] = OrderedDict()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._entries)

    def get_or_compute(self, version: datetime, key: Hashable, compute: Callable[[], Any]) -> Any:
        with self._lock:
            if version != self._version:
                self._entries.clear()
                self._version = version
            if key in self._entries:
                self._entries.move_to_end(key)
                return self._entries[key]
        value = compute()  # outside the lock: a slow query must not block cached answers
        with self._lock:
            if version == self._version:
                self._entries[key] = value
                if len(self._entries) > self._max:
                    self._entries.popitem(last=False)
        return value
