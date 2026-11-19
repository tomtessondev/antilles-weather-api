"""`weather-api load` and `weather-api keys create|revoke|list`."""

from __future__ import annotations

import argparse

import httpx

from weather_api.config import get_settings
from weather_api.db import engine_for
from weather_api.keys import create_key, list_keys, revoke_key
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


def _keys(args: argparse.Namespace) -> None:
    engine = engine_for(get_settings().database_url)
    if args.action == "create":
        key = create_key(engine, args.name, args.per_minute)
        print(f"Key for {args.name} ({args.per_minute} requests a minute), shown once:\n{key}")
    elif args.action == "revoke":
        print("Revoked" if revoke_key(engine, args.name) else f"No active key named {args.name}")
    else:
        for info in list_keys(engine):
            state = f"revoked {info.revoked_at:%Y-%m-%d}" if info.revoked_at else "active"
            print(
                f"{info.name}\t{info.per_minute}/min\tcreated {info.created_at:%Y-%m-%d}\t{state}"
            )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="weather-api")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("load", help="copy the batch marts into the database")
    keys = commands.add_parser("keys", help="manage API keys")
    actions = keys.add_subparsers(dest="action", required=True)
    create = actions.add_parser("create", help="create a key and print it once")
    create.add_argument("--name", required=True)
    create.add_argument("--per-minute", type=int, default=60)
    actions.add_parser("revoke", help="revoke a key by name").add_argument("name")
    actions.add_parser("list", help="list keys (never prints them)")
    args = parser.parse_args(argv)
    if args.command == "load":
        _load()
    else:
        _keys(args)
