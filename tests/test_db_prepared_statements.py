"""Prepared-statement collision regression (quick task 261016-ygc).

Why this file exists
-------------------
Pooling (quick task 261015-lfe) turned out to break Supabase-backed token
routes with::

    psycopg.errors.DuplicatePreparedStatement:
    prepared statement "_pg3_0" already exists

surfacing as 500s on ``GET /api/tokens/mine`` and ``POST /api/admin/revoke``.
The mechanism, confirmed by reading ``psycopg._preparing``:

1. psycopg3 prepares a query server-side after ``prepare_threshold`` (default
   5) executions on one connection, naming it ``_pg3_<n>`` off a
   per-connection counter.
2. psycopg watches every result's ``command_status``; a ``ROLLBACK`` triggers
   ``Prepare.clear()``, which drops the whole cache *and resets the counter
   back to 0* -- see ``_should_discard`` and its
   ``^(?:DROP|ALTER|ROLLBACK|DISCARD ALL|DEALLOCATE ALL)`` matcher.
3. ROLLBACK does **not** deallocate prepared statements server-side. Only
   ``DEALLOCATE ALL`` / ``DISCARD ALL`` do. So psycopg forgets ``_pg3_0``
   while the server still holds it.
4. ``psycopg_pool`` runs ``conn.rollback()`` on *every* connection return,
   i.e. once per ``with connect():`` block. Step 2 therefore fires constantly,
   and once the query crosses the threshold again psycopg re-issues
   ``PREMARE _pg3_0`` against a name the server still has.

Per-operation connections never reached 5 executions, which is why this only
appeared once pooling landed.

The fix is ``prepare_threshold=None`` on every connection. These tests prove
both halves: the config is actually applied, and the cycle that used to raise
now completes cleanly.
"""

import pytest

from kb_mcp import db


# --- The configuration that fixes it ----------------------------------


def test_connection_kwargs_disable_server_side_prepared_statements():
    assert db.CONNECTION_KWARGS["prepare_threshold"] is None


def test_connect_timeout_is_preserved():
    assert db.CONNECTION_KWARGS["connect_timeout"] == 10


def test_pool_is_built_with_the_shared_kwargs(monkeypatch):
    """The pool must not be constructed with a hand-rolled kwargs dict again."""
    captured = {}

    class _FakePool:
        def __init__(self, conninfo=None, **kwargs):
            captured.update(kwargs)

        def close(self):
            pass

    import sys

    monkeypatch.setitem(sys.modules, "psycopg_pool", type("m", (), {"ConnectionPool": _FakePool}))
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://u:p@localhost:5432/db")
    db.close_pool()
    try:
        db.get_pool()
    finally:
        db.close_pool()
    assert captured["kwargs"]["prepare_threshold"] is None


def test_pool_kwargs_are_a_copy_not_the_shared_dict(monkeypatch):
    """A pool mutating its kwargs dict must not corrupt the module constant."""
    captured = {}

    class _GreedyPool:
        def __init__(self, conninfo=None, **kwargs):
            kwargs["kwargs"]["prepare_threshold"] = 99
            captured.update(kwargs)

        def close(self):
            pass

    import sys

    monkeypatch.setitem(sys.modules, "psycopg_pool", type("m", (), {"ConnectionPool": _GreedyPool}))
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://u:p@localhost:5432/db")
    db.close_pool()
    try:
        db.get_pool()
    finally:
        db.close_pool()
    assert db.CONNECTION_KWARGS["prepare_threshold"] is None, "shared dict was mutated"


# --- The cycle that used to raise --------------------------------------


class _RecordingPreparing:
    """A faithful stand-in for psycopg's server-side prepare bookkeeping.

    Reproduces the real naming, threshold and ROLLBACK-driven clear so the
    test asserts against the actual collision logic rather than a paraphrase.
    """

    def __init__(self, prepare_threshold=5):
        self.prepare_threshold = prepare_threshold
        self._names = {}
        self._counts = {}
        self._prepared_idx = 0
        self.server_prepared_names: set[str] = set()

    def execute(self, query: str) -> str | None:
        if self.prepare_threshold is None:
            return None
        if query in self._names:
            return self._names[query]
        count = self._counts.get(query, 0) + 1
        self._counts[query] = count
        if count >= self.prepare_threshold:
            name = f"_pg3_{self._prepared_idx}"
            self._prepared_idx += 1
            if name in self.server_prepared_names:
                raise psycopg_errors_DuplicatePreparedStatement(name)
            self.server_prepared_names.add(name)
            self._names[query] = name
            return name
        return None

    def rollback(self) -> None:
        """Mirror psycopg's _should_discard: ROLLBACK clears the cache."""
        if self._names:
            self._names.clear()
            self._counts.clear()
            self._prepared_idx = 0


class psycopg_errors_DuplicatePreparedStatement(Exception):
    def __init__(self, name):
        super().__init__(f'prepared statement "{name}" already exists')
        self.name = name


QUERY = "SELECT id, token_hash FROM tokens"


def test_pooled_prepare_rollback_cycle_collides_without_the_fix():
    """RED: documents the original failure. Pool + ROLLBACK-on-return breaks."""
    prep = _RecordingPreparing(prepare_threshold=5)  # psycopg's default
    with pytest.raises(psycopg_errors_DuplicatePreparedStatement):
        for _ in range(20):
            prep.execute(QUERY)
            prep.rollback()  # what psycopg_pool does on every connection return


def test_pooled_prepare_rollback_cycle_is_clean_with_the_fix():
    """GREEN: the shipped configuration never prepares, so nothing collides."""
    prep = _RecordingPreparing(prepare_threshold=db.CONNECTION_KWARGS["prepare_threshold"])
    for _ in range(50):
        prep.execute(QUERY)
        prep.rollback()
    assert prep.server_prepared_names == set()