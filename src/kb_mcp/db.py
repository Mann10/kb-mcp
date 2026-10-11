"""Postgres connection helper for the Supabase backend (V2-01).

Connections are short-lived: opened per operation, committed on clean exit,
rolled back on error, always closed. This survives scale-to-zero hosts
(Horizon) with no pooler to manage — correct at personal-KB scale by design.

The connection string comes from ``SUPABASE_DB_URL`` only. It is never logged,
never written to disk, and never given a default.
"""

import contextlib
import os
from collections.abc import Iterator

import psycopg


def db_url() -> str:
    """Return the Postgres connection string, or raise a clear error."""
    url = os.environ.get("SUPABASE_DB_URL")
    if not url or not url.strip():
        raise RuntimeError(
            "SUPABASE_DB_URL is not set: point it at the Supabase Postgres "
            "connection string (Settings > Database > Connection string)."
        )
    return url.strip()


@contextlib.contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """Yield one transactional connection (commit on success, rollback on error)."""
    with psycopg.connect(db_url(), connect_timeout=10) as conn:
        yield conn
