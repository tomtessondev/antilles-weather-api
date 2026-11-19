"""The FastAPI application. `create_app` builds it (tests pass their own engine and clock);
`app` is what uvicorn serves."""

from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine

from weather_api import problems
from weather_api.access import Clock, KeyCache, RateLimiter
from weather_api.cache import ResponseCache
from weather_api.config import Settings, get_settings
from weather_api.db import engine_for
from weather_api.queries import latest_generated_at
from weather_api.routes import data, meta

DESCRIPTION = """
Daily weather and air quality for six towns of Guadeloupe and Martinique, from the
[antilles-data-pipeline](https://github.com/tomtessondev/antilles-data-pipeline) marts,
loaded every morning. Complete days only.

Every `/v1` call needs an API key in the `X-API-Key` header.
"""


def create_app(
    settings: Settings | None = None, engine: Engine | None = None, clock: Clock = time.monotonic
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Antilles Weather API", version="1.0.0", description=DESCRIPTION)
    app.state.settings = settings
    app.state.engine = engine or engine_for(settings.database_url)
    app.state.clock = clock
    app.state.key_cache = KeyCache(clock)
    app.state.limiter = RateLimiter(clock)
    app.state.response_cache = ResponseCache(
        clock, settings.cache_check_seconds, lambda: latest_generated_at(app.state.engine)
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["X-API-Key"]
    )
    problems.install(app)
    app.include_router(meta.router)
    app.include_router(meta.v1)
    app.include_router(data.router)
    return app


app = create_app()
