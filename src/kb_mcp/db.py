"""Postgres connection helper for the Supabase backend (V2-01).

Connections are POOLED. Callers still see the same contract as the original
per-operation helper — one short-lived logical transaction per ``with
connect():`` block, committed on clean exit, rolled back on error — but the
underlying TCP+TLS+auth handshake is paid once per pooled socket instead of
once per operation. ``psycopg_pool`` resets a connection on return and checks
it out healthy, so a connection aborted mid-transaction or killed by a
scale-to-zero Postgres is discarded rather than handed to the next request.

The connection string comes from ``SUPABASE_DB_URL`` only. It is never logged,
never written to disk, and never given a default.
"""

import atexit
import contextlib
import os
import threading
from collections.abc import Iterator

import psycopg

# Module-level pool singleton. Keyed on the db_url() it was built for, so a
# changed environment (tests flip it per-case) rebuilds instead of poisoning.
_pool = None
_pool_url: str | None = None
_pool_lock = threading.Lock()


def db_url() -> str:
    """Return the Postgres connection string, or raise a clear error."""
    url = os.environ.get("SUPABASE_DB_URL")
    if not url or not url.strip():
        raise RuntimeError(
            "SUPABASE_DB_URL is not set: point it at the Supabase Postgres "
            "connection string (Settings > Database > Connection string)."
        )
    return url.strip()


def get_pool():
    """Lazily build and memoize the process-wide ``psycopg_pool`` pool.

    The pool is keyed on :func:`db_url`; if that value changes the old pool is
    closed and a new one built for the new URL. Sizing is deliberately small
    (personal-KB scale) and ``timeout=10`` makes pool exhaustion surface as an
    exception — fail-closed at the repository layer — rather than a hang.

    ``row_factory`` is deliberately left unset: every call site unpacks tuple
    rows (``row[0]``, ``_, title, body, tags, created = row``).

    The ``psycopg_pool`` import is function-local and guarded so a missing
    package degrades to direct connects instead of breaking module import.
    """
    global _pool, _pool_url
    url = db_url()
    with _pool_lock:
        if _pool is not None and _pool_url == url:
            return _pool
        try:
            from psycopg_pool import ConnectionPool  # type: ignore
        except Exception:
            return None
        if _pool is not None:
            try:
                _pool.close()
            except Exception:
                pass
        # min_size=1 keeps a warm socket; max_size=10 caps concurrent
        # connections; timeout=10 turns saturation into a loud failure.
        _pool = ConnectionPool(
            conninfo=url,
            min_size=1,
            max_size=10,
            timeout=10,
            open=True,
            kwargs={"connect_timeout": 10},
        )
        _pool_url = url
        return _pool


def close_pool() -> None:
    """Close and forget the pool. Idempotent, never raises."""
    global _pool, _pool_url
    with _pool_lock:
        pool = _pool
        _pool = None
        _pool_url = None
    if pool is not None:
        try:
            pool.close()
        except Exception:
            pass


atexit.register(close_pool)


@contextlib.contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """Yield one transactional connection (commit on success, rollback on error).

    Drop-in for the historical per-operation helper: the signature, the
    contextmanager decorator and the transaction semantics are unchanged, so
    all existing ``with connect() as conn:`` call sites keep working
    untouched. ``pool.connection()`` commits on clean exit and rolls back when
    the body raises — exactly what those call sites already relied on.
    """
    try:
        pool = get_pool()
    except Exception:
        pool = None
    if pool is None:
        # psycopg_pool unavailable: today's behavior, correctness unchanged.
        with psycopg.connect(db_url(), connect_timeout=10) as conn:
            yield conn
        return
    with pool.connection() as conn:
        yield conn