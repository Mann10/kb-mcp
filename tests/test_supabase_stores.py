"""Supabase tokens/templates/audit backend tests (V2-02).

Needs a live Postgres: set SUPABASE_DB_URL (pooler URL works). Without it
(or when unreachable) the whole module skips — normal unit runs unaffected.

The session fixture applies all migrations itself (idempotent). Usernames and
template names are unique per test with cleanup afterwards.
"""

import os
import uuid

import pytest

from kb_mcp.auth import TokenType

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_DB_URL"),
    reason="SUPABASE_DB_URL not set — live Supabase tests skipped",
)

_MIGRATIONS = ("0001_notes.sql", "0002_tokens.sql", "0003_templates_audit.sql")


def _can_connect():
    from kb_mcp.db import connect

    try:
        with connect():
            return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def live_db():
    if not _can_connect():
        pytest.skip("Supabase unreachable — live Supabase tests skipped")
    from pathlib import Path

    from kb_mcp.db import connect

    mig_dir = Path(__file__).resolve().parent.parent / "supabase" / "migrations"
    with connect() as conn, conn.cursor() as cur:
        for name in _MIGRATIONS:
            lines = (mig_dir / name).read_text(encoding="utf-8").splitlines()
            code = "\n".join(
                line for line in lines if not line.lstrip().startswith("--")
            )
            for stmt in (s.strip() for s in code.split(";")):
                if stmt:
                    cur.execute(stmt)
    return True


@pytest.fixture
def tstore(live_db):
    from kb_mcp.supabase_auth import SupabaseTokenStore

    return SupabaseTokenStore.load()


@pytest.fixture
def tmpl_store(live_db):
    from kb_mcp.supabase_templates import SupabaseTemplateStore

    return SupabaseTemplateStore.load()


@pytest.fixture
def user():
    return f"v2t-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def cleanup(live_db, user):
    yield
    from kb_mcp.db import connect

    with connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM tokens WHERE username LIKE %s", (user + "%",))
        cur.execute("DELETE FROM audit_log WHERE username LIKE %s", (user + "%",))


@pytest.fixture
def template_cleanup(live_db):
    created: list[str] = []
    yield created
    from kb_mcp.db import connect

    with connect() as conn, conn.cursor() as cur:
        for name in created:
            cur.execute("DELETE FROM templates WHERE name = %s", (name,))


def _raw_token_rows():
    """All stored token text for the secrecy proof (hashes only, never raw)."""
    from kb_mcp.db import connect

    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT key_hash, key_prefix, key_suffix, username FROM tokens")
        return cur.fetchall()


# --- tokens ---


def test_token_add_lookup_roundtrip(tstore, user):
    raw, entry = tstore.add_token(user, TokenType.READ_WRITE)
    assert len(raw) > 16
    found = tstore.lookup(raw)
    assert found is not None
    assert found.username == user
    assert found.token_type is TokenType.READ_WRITE
    assert found.scopes == ["notes:read", "notes:write"]


def test_token_lookup_denies_unknown(tstore):
    assert tstore.lookup("definitely-not-a-real-token-0000") is None
    assert tstore.lookup(None) is None
    assert tstore.lookup("   ") is None


def test_token_hashes_only_on_db(tstore, user):
    raw, entry = tstore.add_token(user, TokenType.READ)
    for row in _raw_token_rows():
        for field in row:
            assert raw not in (field or "")
    assert entry.key_hash != raw


def test_token_revoke(tstore, user):
    raw, entry = tstore.add_token(user, TokenType.READ)
    assert tstore.lookup(raw) is not None
    tstore.revoke_by_prefix(entry.key_prefix[:4])
    assert tstore.lookup(raw) is None


def test_token_revoke_unknown_prefix(tstore):
    with pytest.raises(KeyError):
        tstore.revoke_by_prefix("zzzz-no-match")


def test_token_ambiguous_prefix_rejected(tstore, user):
    tstore.add_token(user + "-a", TokenType.READ, raw="sharedtok-aaa-00000001")
    tstore.add_token(user + "-b", TokenType.READ, raw="sharedtok-bbb-00000002")
    with pytest.raises(KeyError):
        tstore.revoke_by_prefix("shared")


def test_token_rotate_preserves_identity(tstore, user):
    raw, entry = tstore.add_token(
        user, TokenType.READ_WRITE, expires_at="2030-01-01T00:00:00+00:00"
    )
    new_raw, new_entry = tstore.rotate_by_prefix(entry.key_prefix[:6])
    assert new_raw != raw
    assert tstore.lookup(raw) is None
    found = tstore.lookup(new_raw)
    assert found is not None and found.username == user
    assert found.expires_at == "2030-01-01T00:00:00+00:00"


def test_token_expired_denied_and_filtered(tstore, user):
    raw, _ = tstore.add_token(
        user, TokenType.READ, expires_at="2000-01-01T00:00:00+00:00"
    )
    assert tstore.lookup(raw) is None
    assert all(e.username != user for e in tstore.list_entries())
    assert any(e.username == user for e in tstore.list_entries(True))


def test_token_unparsable_expiry_denied(tstore, user):
    raw, _ = tstore.add_token(user, TokenType.READ, expires_at="not-a-date")
    assert tstore.lookup(raw) is None


def test_token_list_sorted_and_filtered(tstore, user):
    tstore.add_token(user + "-b", TokenType.READ)
    tstore.add_token(user + "-a", TokenType.READ)
    mine = [e for e in tstore.list_entries() if e.username.startswith(user)]
    assert {e.username for e in mine} == {user + "-b", user + "-a"}
    assert [e.created_at for e in mine] == sorted(e.created_at for e in mine)


def test_token_update_last_used(tstore, user):
    from kb_mcp.auth import TokenStore as _TS  # noqa: F401 (contract import)

    raw, _ = tstore.add_token(user, TokenType.READ)
    tstore.update_last_used(raw)
    assert tstore.lookup(raw).last_used_at is not None
    tstore.update_last_used("nope-not-a-token")  # must not raise


# --- templates ---


def test_templates_seed_builtins(tmpl_store):
    assert {"meeting", "book", "idea"} <= set(tmpl_store.names())
    assert tmpl_store.get("meeting")["default_tags"] == ["meeting"]


def test_template_crud(tmpl_store, template_cleanup):
    name = f"v2tpl-{uuid.uuid4().hex[:8]}"
    template_cleanup.append(name)
    assert tmpl_store.get(name) is None
    tmpl_store.add(name, "# Hi", ["x"])
    assert tmpl_store.get(name) == {"default_tags": ["x"], "body_skeleton": "# Hi"}
    with pytest.raises(KeyError):
        tmpl_store.add(name, "# Dup", [])
    tmpl_store.update(name, body_skeleton="# Updated")
    assert tmpl_store.get(name)["body_skeleton"] == "# Updated"
    tmpl_store.update(name, default_tags=["y", "z"])
    assert tmpl_store.get(name)["default_tags"] == ["y", "z"]
    assert name in tmpl_store.names()
    assert tmpl_store.names() == sorted(tmpl_store.names())
    tmpl_store.remove(name)
    assert tmpl_store.get(name) is None
    with pytest.raises(KeyError):
        tmpl_store.remove(name)
    with pytest.raises(KeyError):
        tmpl_store.update(name, body_skeleton="x")


def test_template_seed_idempotent(tmpl_store):
    before = len(tmpl_store)
    type(tmpl_store).load()
    assert len(tmpl_store) == before


# --- audit ---


def test_audit_write_db_roundtrip(live_db, user):
    from kb_mcp.db import connect
    from kb_mcp.supabase_audit import audit_write_db

    audit_write_db(user, "create_note", "hello.md")
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT username, tool, filename FROM audit_log WHERE username = %s",
            (user,),
        )
        assert cur.fetchone() == (user, "create_note", "hello.md")


def test_audit_write_db_fail_open(monkeypatch):
    import kb_mcp.supabase_audit as audit_mod

    def _boom():
        raise ConnectionError("db down")

    monkeypatch.setattr(audit_mod, "connect", _boom)
    assert audit_mod.audit_write_db("u", "t", "f.md") is None
