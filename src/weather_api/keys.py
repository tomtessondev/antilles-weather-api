"""API keys. A key is shown once when created; only its SHA-256 is stored, so a leaked
database does not leak keys. `KeyInfo` never carries the key or its hash."""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine, insert, select, update

from weather_api.db import api_keys

KEY_PATTERN = re.compile(r"^aw_[A-Za-z0-9_-]{43}$")


@dataclass(frozen=True)
class KeyInfo:
    name: str
    per_minute: int
    created_at: datetime
    revoked_at: datetime | None


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def create_key(engine: Engine, name: str, per_minute: int) -> str:
    key = f"aw_{secrets.token_urlsafe(32)}"  # 32 bytes → 43 url-safe characters
    with engine.begin() as conn:
        conn.execute(
            insert(api_keys).values(
                name=name,
                key_hash=hash_key(key),
                per_minute=per_minute,
                created_at=datetime.now(UTC),
            )
        )
    return key


def revoke_key(engine: Engine, name: str) -> bool:
    with engine.begin() as conn:
        result = conn.execute(
            update(api_keys)
            .where(api_keys.c.name == name, api_keys.c.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
    return result.rowcount > 0


# Same order as KeyInfo's fields.
_COLUMNS = (api_keys.c.name, api_keys.c.per_minute, api_keys.c.created_at, api_keys.c.revoked_at)


def list_keys(engine: Engine) -> list[KeyInfo]:
    with engine.connect() as conn:
        return [KeyInfo(*row) for row in conn.execute(select(*_COLUMNS).order_by(api_keys.c.name))]


def find_key(engine: Engine, key_hash: str) -> KeyInfo | None:
    """The active key with this hash, if any."""
    with engine.connect() as conn:
        row = conn.execute(
            select(*_COLUMNS).where(
                api_keys.c.key_hash == key_hash, api_keys.c.revoked_at.is_(None)
            )
        ).first()
    return KeyInfo(*row) if row else None
