"""The first migration creates the tables the loader and the API use."""

from __future__ import annotations

from sqlalchemy import Engine, inspect


def test_migration_creates_the_tables(db: Engine) -> None:
    schema = inspect(db)
    assert set(schema.get_table_names()) >= {
        "locations", "daily_weather", "daily_air_quality", "loads", "api_keys",
    }  # fmt: skip
    for table in ("daily_weather", "daily_air_quality"):
        pk = schema.get_pk_constraint(table)["constrained_columns"]
        assert pk == ["location_code", "observed_date"]
        indexed = [i["column_names"] for i in schema.get_indexes(table)]
        assert ["observed_date", "location_code"] in indexed
    assert {u["column_names"][0] for u in schema.get_unique_constraints("api_keys")} >= {
        "name", "key_hash",
    }  # fmt: skip
