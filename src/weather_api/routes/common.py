"""What the routes share: the data state from the snapshot, and the answer cache."""

from __future__ import annotations

from collections.abc import Callable, Hashable
from datetime import datetime

from fastapi import Request, Response

from weather_api.cache import ResponseCache
from weather_api.problems import DataUnavailable
from weather_api.snapshot import Snapshot, State

CACHE_CONTROL = "public, max-age=300"


def loaded_state(request: Request) -> tuple[State, datetime]:
    """The snapshot, and the `generated_at` of the data it describes; 503 before the
    first load."""
    snapshot: Snapshot = request.app.state.snapshot
    state = snapshot.get()
    if state.generated_at is None:
        raise DataUnavailable("No data loaded yet; the first daily load has not run.")
    return state, state.generated_at


def cached[T](request: Request, response: Response, key: Hashable, compute: Callable[[], T]) -> T:
    """`compute()` once per data version and `key`; errors are not cached."""
    _, version = loaded_state(request)
    cache: ResponseCache = request.app.state.response_cache
    response.headers["Cache-Control"] = CACHE_CONTROL
    result: T = cache.get_or_compute(version, key, compute)
    return result
