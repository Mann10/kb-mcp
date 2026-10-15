"""Connection-pool proofs for :mod:`kb_mcp.db` (261015-lfe task 1).

Hermetic: a fake ``ConnectionPool`` is injected, so no live database, no
network, no SUPABASE_DB_URL required. The proofs target the contract the 31
existing ``with connect() as conn:`` call sites depend on: same signature,
commit on clean exit, rollback on raise, and a pool that is reused rather
than re-dialed.
"""

import pytest

from kb_mcp import db


class _FakeCursor:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, *_args, **_kwargs):
        self._conn.executed.append(True)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _FakeConn:
    def __init__(self, pool):
        self._pool = pool
        self.executed = []
        self.closed = False

    def cursor(self):
        return _FakeCursor(self)

    def close(self):
        self.closed = True


class _FakePoolConnection:
    """Mimics psycopg_pool's connection context manager semantics."""

    def __init__(self, pool):
        self._pool = pool
        self._conn = None

    def __enter__(self):
        self._pool.checkouts += 1
        self._conn = _FakeConn(self._pool)
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._pool.commits += 1
        else:
            self._pool.rollbacks += 1
        self._pool.returns += 1
        if self._conn is not None:
            self._conn.closed = True
        return False


class _FakePool:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.checkouts = 0
        self.commits = 0
        self.rollbacks = 0
        self.returns = 0
        self.closed = False
        self.resets = 0

    def connection(self):
        return _FakePoolConnection(self)

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _clean_pool_state(monkeypatch):
    """Every test starts and ends with no pool and a recorded env value."""
    db.close_pool()
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://user:pw@host:5432/db")
    yield
    db.close_pool()


@pytest.fixture()
def fake_pool(monkeypatch):
    """Install a fake psycopg_pool module exposing a counting ConnectionPool."""
    import sys
    import types

    created: list[_FakePool] = []

    class ConnectionPool(_FakePool):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            created.append(self)

    module = types.ModuleType("psycopg_pool")
    module.ConnectionPool = ConnectionPool  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "psycopg_pool", module)
    return created


# --- (a) pool reuse -----------------------------------------------------


def test_two_connects_reuse_one_pool_without_dialing(monkeypatch, fake_pool):
    import psycopg

    def _boom(*_args, **_kwargs):  # pragma: no cover - must never run
        raise AssertionError("psycopg.connect called — pool was not reused")

    monkeypatch.setattr(psycopg, "connect", _boom)
    with db.connect() as conn1:
        conn1.cursor().execute("SELECT 1")
    with db.connect() as conn2:
        conn2.cursor().execute("SELECT 1")
    assert len(fake_pool) == 1
    assert fake_pool[0].checkouts == 2
    assert fake_pool[0].returns == 2


# --- (b) identity stability --------------------------------------------


def test_get_pool_returns_identical_object(fake_pool):
    assert db.get_pool() is db.get_pool()


# --- (c) env-keyed rebuild ---------------------------------------------


def test_url_change_rebuilds_pool(monkeypatch, fake_pool):
    first = db.get_pool()
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://user:pw@other:5432/db2")
    second = db.get_pool()
    assert second is not first
    assert len(fake_pool) == 2
    assert first.closed is True
    assert second.closed is False


def test_pool_construction_parameters(fake_pool):
    pool = db.get_pool()
    assert pool.kwargs["min_size"] == 1
    assert pool.kwargs["max_size"] == 10
    assert pool.kwargs["timeout"] == 10
    assert pool.kwargs["kwargs"]["connect_timeout"] == 10
    # row_factory must stay unset: call sites unpack tuple rows
    assert "row_factory" not in pool.kwargs
    assert pool.kwargs["conninfo"] == "postgresql://user:pw@host:5432/db"


# --- (d) transaction semantics -----------------------------------------


def test_connect_commits_on_clean_exit(fake_pool):
    with db.connect():
        pass
    assert fake_pool[0].commits == 1
    assert fake_pool[0].rollbacks == 0


def test_connect_rolls_back_when_body_raises(fake_pool):
    with pytest.raises(ValueError):
        with db.connect():
            raise ValueError("boom")
    assert fake_pool[0].rollbacks == 1
    assert fake_pool[0].commits == 0


# --- (e) db_url contract unchanged -------------------------------------


def test_db_url_raises_when_env_missing(monkeypatch):
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    with pytest.raises(RuntimeError, match="SUPABASE_DB_URL is not set"):
        db.db_url()


def test_db_url_raises_when_blank(monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", "   ")
    with pytest.raises(RuntimeError, match="SUPABASE_DB_URL is not set"):
        db.db_url()


# --- (f) teardown ------------------------------------------------------


def test_close_pool_is_idempotent_and_resets(fake_pool):
    pool = db.get_pool()
    db.close_pool()
    db.close_pool()
    assert pool.closed is True
    assert db._pool is None
    assert db._pool_url is None


def test_connect_after_close_pool_rebuilds_transparently(fake_pool):
    with db.connect():
        pass
    db.close_pool()
    with db.connect():
        pass
    assert len(fake_pool) == 2


# --- regression: pool reused across repository-shaped work -------------


def test_pool_reused_across_many_connect_blocks(fake_pool):
    for _ in range(5):
        with db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT stem FROM notes ORDER BY stem")
    assert len(fake_pool) == 1
    assert fake_pool[0].checkouts == 5


def test_missing_psycopg_pool_falls_back_to_direct_connect(monkeypatch):
    """If the pool package is unavailable, connect() degrades, never breaks."""
    import builtins
    import sys

    monkeypatch.setitem(sys.modules, "psycopg_pool", None)

    real_import = builtins.__import__

    def _no_pool(name, *args, **kwargs):
        if name == "psycopg_pool":
            raise ImportError("no psycopg_pool")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_pool)
    assert db.get_pool() is None

    import psycopg

    seen = {}

    class _DirectConn:
        def __enter__(self):
            seen["opened"] = True
            return self

        def __exit__(self, *_exc):
            return False

        def cursor(self):
            raise AssertionError("cursor not needed for this proof")

    monkeypatch.setattr(
        psycopg, "connect", lambda *_a, **_k: _DirectConn()
    )
    with db.connect() as conn:
        assert conn is not None
    assert seen.get("opened") is True