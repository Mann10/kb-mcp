"""Supabase notes backend tests (V2-01).

Needs a live Postgres: set SUPABASE_DB_URL. Without it (or when unreachable)
the whole module skips — normal unit runs are unaffected.

The session fixture applies `supabase/migrations/0001_notes.sql` itself
(idempotent), so tests need nothing but the URL. Stems are unique per test
and cleaned up afterwards; concurrent runs never collide.
"""

import os
import uuid

import pytest

from kb_mcp.errors import InvalidTypeError, NoteNotFoundError

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_DB_URL"),
    reason="SUPABASE_DB_URL not set — live Supabase tests skipped",
)


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

    sql = (
        Path(__file__).resolve().parent.parent
        / "supabase"
        / "migrations"
        / "0001_notes.sql"
    ).read_text(encoding="utf-8")
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
    return True


@pytest.fixture
def repo(live_db):
    from kb_mcp.supabase_notes import SupabaseNoteRepository

    return SupabaseNoteRepository()


@pytest.fixture
def stem():
    return f"t{uuid.uuid4().hex[:8]}"


@pytest.fixture
def note_file(stem):
    return f"{stem}-note.md"


@pytest.fixture(autouse=True)
def cleanup(live_db, stem):
    yield
    from kb_mcp.db import connect

    with connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM note_revisions WHERE stem LIKE %s", (stem + "%",))
        cur.execute("DELETE FROM notes WHERE stem LIKE %s", (stem + "%",))


def _revisions(stem_prefix, action=None):
    from kb_mcp.db import connect

    with connect() as conn, conn.cursor() as cur:
        if action:
            cur.execute(
                "SELECT stem, action, old_stem, new_stem, actor FROM note_revisions "
                "WHERE stem LIKE %s AND action = %s ORDER BY id",
                (stem_prefix + "%", action),
            )
        else:
            cur.execute(
                "SELECT stem, action, old_stem, new_stem, actor FROM note_revisions "
                "WHERE stem LIKE %s ORDER BY id",
                (stem_prefix + "%",),
            )
        return cur.fetchall()


def test_write_read_roundtrip(repo, note_file):
    note = repo.write_note(
        note_file, "Hello World", "Body text.", ["a", "b"], "2026-10-11", actor="tester"
    )
    assert note.filename == note_file[:-3]
    fetched = repo.read_note(note_file)
    assert fetched.metadata.title == "Hello World"
    assert fetched.body == "Body text."
    assert fetched.metadata.tags == ["a", "b"]
    assert fetched.metadata.created == "2026-10-11"


def test_write_is_upsert(repo, note_file):
    repo.write_note(note_file, "First", "one", [], "2026-10-11", actor="tester")
    repo.write_note(note_file, "Second", "two", [], "2026-10-12", actor="tester")
    assert repo.read_note(note_file).metadata.title == "Second"
    assert repo.read_note(note_file).body == "two"


def test_read_missing_raises(repo):
    with pytest.raises(NoteNotFoundError):
        repo.read_note("t00000000-nope.md")


def test_invalid_filename_rejected(repo):
    with pytest.raises(InvalidTypeError):
        repo.read_note("../evil.md")


def test_bad_metadata_rejected_without_write(repo, note_file, stem):
    with pytest.raises(ValueError):
        repo.write_note(note_file, "   ", "x", [], "2026-10-11", actor="tester")
    with pytest.raises(NoteNotFoundError):
        repo.read_note(note_file)
    assert _revisions(stem) == []


def test_list_created_ascending(repo, stem):
    repo.write_note(f"{stem}-b.md", "B", "", [], "2026-10-12", actor="tester")
    repo.write_note(f"{stem}-a.md", "A", "", [], "2026-10-10", actor="tester")
    titles = [
        n.title
        for n in repo.list_notes()
        if n.title in ("A", "B")
    ]
    assert titles == ["A", "B"]


def test_update_body_only(repo, note_file, stem):
    repo.write_note(note_file, "T", "old", ["x"], "2026-10-11", actor="tester")
    updated = repo.update_note(note_file, body="new", actor="tester")
    assert updated.body == "new"
    assert updated.metadata.title == "T"
    revs = _revisions(stem, "update")
    assert len(revs) == 1 and revs[0][4] == "tester"


def test_rename_moves_row_and_records_history(repo, note_file, stem):
    repo.write_note(note_file, f"{stem} Old", "b", [], "2026-10-11", actor="tester")
    renamed = repo.update_note(note_file, title=f"{stem} New", actor="tester")
    assert renamed.filename == f"{stem}-new"
    with pytest.raises(NoteNotFoundError):
        repo.read_note(note_file)
    assert repo.read_note(f"{stem}-new.md").body == "b"
    revs = _revisions(stem, "rename")
    assert len(revs) == 1
    _, _, old_stem, new_stem, actor = revs[0]
    assert old_stem == note_file[:-3] and new_stem == f"{stem}-new"
    assert actor == "tester"


def test_rename_collision_rejected(repo, stem):
    repo.write_note(f"{stem}-one.md", f"{stem} One", "", [], "2026-10-11", actor="t")
    repo.write_note(f"{stem}-two.md", f"{stem} Two", "", [], "2026-10-11", actor="t")
    with pytest.raises(FileExistsError):
        repo.update_note(f"{stem}-one.md", title=f"{stem} Two", actor="t")


def test_rename_bad_slug_rejected(repo, note_file):
    repo.write_note(note_file, "Fine", "", [], "2026-10-11", actor="tester")
    with pytest.raises(InvalidTypeError):
        repo.update_note(note_file, title="!!!", actor="tester")


def test_delete_removes_row_and_snapshots_state(repo, note_file, stem):
    repo.write_note(note_file, "Gone", "bye", ["z"], "2026-10-11", actor="tester")
    repo.delete_note(note_file, actor="tester")
    with pytest.raises(NoteNotFoundError):
        repo.read_note(note_file)
    from kb_mcp.db import connect

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT title, body, actor FROM note_revisions "
            "WHERE stem LIKE %s AND action = 'delete'",
            (stem + "%",),
        )
        row = cur.fetchone()
    assert row == ("Gone", "bye", "tester")


def test_delete_missing_raises(repo):
    with pytest.raises(NoteNotFoundError):
        repo.delete_note("t00000000-nope.md", actor="tester")


def test_create_revision_captures_actor(repo, note_file, stem):
    repo.write_note(note_file, "T", "", [], "2026-10-11", actor="alice")
    revs = _revisions(stem, "create")
    assert len(revs) == 1 and revs[0][4] == "alice"


def test_db_url_missing_raises(monkeypatch):
    from kb_mcp import db

    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    with pytest.raises(RuntimeError):
        db.db_url()
