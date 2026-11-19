"""Who may call, and how often, without waking the database: a malformed key is refused on
its shape, a well-formed one is looked up among the active keys held in memory (see
`snapshot`), and the per-key quota is counted in memory (per instance: with at most two
instances, a key gets at most twice its quota)."""

from __future__ import annotations

import math
import threading
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import APIKeyHeader

from weather_api.keys import KEY_PATTERN, KeyInfo, hash_key
from weather_api.snapshot import Clock, Snapshot

API_KEY = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="Your API key; the demo key in the API description works with a low quota.",
)


class RateLimiter:
    """A fixed window per key: `limit` calls per `window_seconds`. Only valid keys reach
    it, so its memory is bounded by the number of keys."""

    def __init__(self, clock: Clock, window_seconds: float = 60) -> None:
        self._clock, self._window = clock, window_seconds
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def hit(self, key_hash: str, limit: int) -> tuple[bool, int, int]:
        """(allowed, remaining, seconds until the window resets)."""
        with self._lock:
            now = self._clock()
            start, count = self._windows.get(key_hash, (now, 0))
            if now - start >= self._window:
                start, count = now, 0
            retry_after = max(1, math.ceil(start + self._window - now))
            if count >= limit:
                return False, 0, retry_after
            self._windows[key_hash] = (start, count + 1)
            return True, limit - count - 1, retry_after


def require_key(
    request: Request, response: Response, key: Annotated[str | None, Depends(API_KEY)]
) -> KeyInfo:
    if key is None or not KEY_PATTERN.fullmatch(key):
        raise HTTPException(401, "Send a valid API key in the X-API-Key header.")
    snapshot: Snapshot = request.app.state.snapshot
    key_hash = hash_key(key)
    info = snapshot.get().keys.get(key_hash)
    if info is None:
        raise HTTPException(401, "This API key is unknown or revoked.")
    limiter: RateLimiter = request.app.state.limiter
    allowed, remaining, retry_after = limiter.hit(key_hash, info.per_minute)
    limit_headers = {"RateLimit-Limit": str(info.per_minute), "RateLimit-Remaining": str(remaining)}
    if not allowed:
        raise HTTPException(
            429,
            f"Quota of {info.per_minute} requests a minute reached.",
            {**limit_headers, "Retry-After": str(retry_after)},
        )
    response.headers.update(limit_headers)
    return info
