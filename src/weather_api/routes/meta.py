"""Health, data freshness and towns: answered from memory (snapshot and cache)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select

from weather_api.access import require_key
from weather_api.db import locations
from weather_api.routes.common import cached, loaded_state
from weather_api.snapshot import Snapshot

router = APIRouter()
v1 = APIRouter(prefix="/v1", dependencies=[Depends(require_key)])


class Health(BaseModel):
    status: Literal["ok"]


class Meta(BaseModel):
    generated_at: datetime
    loaded_at: datetime


class Location(BaseModel):
    location_code: str
    town: str
    territory: Literal["Guadeloupe", "Martinique"]
    latitude: float
    longitude: float


@router.get(
    "/health",
    tags=["health"],
    summary="The service answers, and its database answered at the last refresh (≤ 15 min)",
)
def health(request: Request) -> Health:
    snapshot: Snapshot = request.app.state.snapshot
    snapshot.get()  # reads the database only when the snapshot is due; fails with 503
    return Health(status="ok")


@v1.get("/meta", tags=["meta"], summary="When the data served was produced and loaded")
def meta(request: Request) -> Meta:
    state, generated_at = loaded_state(request)
    assert state.loaded_at is not None  # set together with generated_at
    return Meta(generated_at=generated_at, loaded_at=state.loaded_at)


def _all_locations(request: Request) -> list[Location]:
    with request.app.state.engine.connect() as conn:
        rows = conn.execute(select(locations).order_by(locations.c.location_code))
        return [Location(**row._mapping) for row in rows]


@v1.get("/locations", tags=["towns"], summary="The six towns")
def list_locations(request: Request, response: Response) -> list[Location]:
    return cached(request, response, ("locations",), lambda: _all_locations(request))


@v1.get("/locations/{code}", tags=["towns"], summary="One town")
def get_location(request: Request, response: Response, code: str) -> Location:
    state, _ = loaded_state(request)
    if code not in state.codes:
        raise HTTPException(404, f"No town with code {code!r}.")
    towns = cached(request, response, ("locations",), lambda: _all_locations(request))
    return next(t for t in towns if t.location_code == code)
