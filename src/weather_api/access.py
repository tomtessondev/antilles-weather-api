"""Who may call, and how often, without waking the database for nothing: a malformed key is
refused on its shape, known key hashes are cached for a minute, and the per-key quota is
counted in memory (per instance: with at most two instances, a key gets at most twice its
quota)."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import APIKeyHeader

from weather_api.keys import KEY_PATTERN, KeyInfo, find_key, hash_key

Clock = Callable[[], float]
API_KEY = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="Your API key. The demo key in the API description works with a low quota.",
)


class KeyCache:
    """Active keys (or their absence) by hash, kept `ttl_seconds`."""

    def __init__(self, clock: Clock, ttl_seconds: float = 60) -> None:
        self._clock, self._ttl = clock, ttl_seconds
        self._entries: dict[str, tuple[float, KeyInfo | None]] = {}

    def get(self, key_hash: str) -> tuple[bool, KeyInfo | None]:
        entry = self._entries.get(key_hash)
        if entry is None or self._clock() - entry[0] >= self._ttl:
            return False, None
        return True, entry[1]

    def put(self, key_hash: str, info: KeyInfo | None) -> None:
        self._entries[key_hash] = (self._clock(), info)


class RateLimiter:
    """A fixed window per key: `limit` calls per `window_seconds`."""

    def __init__(self, clock: Clock, window_seconds: float = 60) -> None:
        self._clock, self._window = clock, window_seconds
        self._windows: dict[str, tuple[float, int]] = {}

    def hit(self, key_hash: str, limit: int) -> tuple[bool, int, int]:
        """(allowed, remaining, seconds until the window resets)."""
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
    state = request.app.state
    cache: KeyCache = state.key_cache
    limiter: RateLimiter = state.limiter
    key_hash = hash_key(key)
    cached, info = cache.get(key_hash)
    if not cached:
        info = find_key(state.engine, key_hash)
        cache.put(key_hash, info)
    if info is None:
        raise HTTPException(401, "This API key is unknown or revoked.")
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
