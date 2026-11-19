"""Health, data freshness and towns."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, text

from weather_api.access import require_key
from weather_api.db import loads, locations
from weather_api.problems import DataUnavailable

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


@router.get("/health", tags=["health"], summary="The service and its database answer")
def health(request: Request) -> Health:
    with request.app.state.engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return Health(status="ok")


def latest_load(request: Request) -> Meta:
    with request.app.state.engine.connect() as conn:
        row = conn.execute(
            select(loads.c.generated_at, loads.c.loaded_at).order_by(loads.c.generated_at.desc())
        ).first()
    if row is None:
        raise DataUnavailable("No data loaded yet; the first daily load has not run.")
    return Meta(generated_at=row.generated_at, loaded_at=row.loaded_at)


@v1.get("/meta", tags=["meta"], summary="When the data served was produced and loaded")
def meta(current: Annotated[Meta, Depends(latest_load)]) -> Meta:
    return current


@v1.get("/locations", tags=["towns"], summary="The six towns")
def list_locations(request: Request) -> list[Location]:
    with request.app.state.engine.connect() as conn:
        rows = conn.execute(select(locations).order_by(locations.c.location_code))
        return [Location(**row._mapping) for row in rows]


@v1.get("/locations/{code}", tags=["towns"], summary="One town")
def get_location(request: Request, code: str) -> Location:
    with request.app.state.engine.connect() as conn:
        row = conn.execute(select(locations).where(locations.c.location_code == code)).first()
    if row is None:
        raise HTTPException(404, f"No town with code {code!r}.")
    return Location(**row._mapping)
