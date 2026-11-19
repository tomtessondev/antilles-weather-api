"""API keys: shown once, stored as a hash, revocable."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError

from weather_api.db import api_keys
from weather_api.keys import KEY_PATTERN, create_key, find_key, hash_key, list_keys, revoke_key


def test_created_key_matches_the_pattern_and_only_its_hash_is_stored(db: Engine) -> None:
    key = create_key(db, "demo", per_minute=60)
    assert KEY_PATTERN.fullmatch(key)
    with db.connect() as conn:
        stored = conn.execute(select(api_keys.c.key_hash)).scalar_one()
    assert stored == hash_key(key) and key not in stored
    found = find_key(db, hash_key(key))
    assert found is not None and (found.name, found.per_minute) == ("demo", 60)


def test_revoked_key_is_not_found(db: Engine) -> None:
    key = create_key(db, "client", per_minute=120)
    assert revoke_key(db, "client") is True
    assert find_key(db, hash_key(key)) is None
    assert revoke_key(db, "nobody") is False


def test_list_never_shows_keys(db: Engine) -> None:
    key = create_key(db, "demo", per_minute=60)
    (info,) = list_keys(db)
    assert info.name == "demo" and info.revoked_at is None
    assert key not in repr(info) and hash_key(key) not in repr(info)


def test_duplicate_name_is_refused(db: Engine) -> None:
    create_key(db, "demo", per_minute=60)
    with pytest.raises(IntegrityError):
        create_key(db, "demo", per_minute=60)
