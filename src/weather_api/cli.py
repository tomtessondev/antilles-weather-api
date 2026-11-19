"""`weather-api load` and `weather-api keys create|revoke|list`."""

from __future__ import annotations

import argparse

import httpx

from weather_api.config import get_settings
from weather_api.db import engine_for
from weather_api.load import fetch_marts, load_marts


def _load() -> None:
    settings = get_settings()
    with httpx.Client() as client:
        marts = fetch_marts(client, settings.marts_url)
    result = load_marts(engine_for(settings.database_url), marts)
    if result.skipped:
        print(f"Already loaded: marts generated at {marts.generated_at.isoformat()}")
    else:
        print(
            f"Loaded marts generated at {marts.generated_at.isoformat()}: {result.locations} "
            f"towns, {result.weather_rows} weather rows, {result.air_quality_rows} air-quality rows"
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="weather-api")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("load", help="copy the batch marts into the database")
    args = parser.parse_args(argv)
    if args.command == "load":
        _load()
