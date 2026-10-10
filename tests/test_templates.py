"""WRITE-07 proofs: create_from_template over an isolated repo (no mocks)."""

import datetime

import pytest

from kb_mcp import write_tools
from kb_mcp.errors import AuthenticationError, AuthorizationError
from kb_mcp.middleware import INVALID_TOKEN_MESSAGE, WRITE_DENIED_MESSAGE


@pytest.fixture(autouse=True)
def _use_isolated_repo(repository):
    write_tools.configure_default_repo(repository)
    yield
    write_tools.configure_default_repo(None)


def _w(token_store, read_write_token_pair):
    raw, _ = read_write_token_pair
    return raw, token_store


def test_meeting_default(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.create_from_template("meeting", "Sync Notes", token=raw, _store=store)
    assert out["success"] is True
    assert out["filename"] == "sync-notes"
    assert "meeting" in out["tags"]
    assert out["created"] == datetime.date.today().isoformat()
    note = repository.read_note("sync-notes.md")
    assert "## Attendees" in note.body
    assert (repository.notes_dir / "sync-notes.md").exists()


def test_book_default(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.create_from_template("book", "Deep Work", token=raw, _store=store)
    assert out["success"] is True
    assert out["filename"] == "deep-work"
    assert "book" in out["tags"]
    assert out["created"] == datetime.date.today().isoformat()
    note = repository.read_note("deep-work.md")
    assert "## Key Takeaways" in note.body
    assert (repository.notes_dir / "deep-work.md").exists()


def test_idea_default(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.create_from_template("idea", "Flying Cars", token=raw, _store=store)
    assert out["success"] is True
    assert out["filename"] == "flying-cars"
    assert "idea" in out["tags"]
    assert out["created"] == datetime.date.today().isoformat()
    note = repository.read_note("flying-cars.md")
    assert "## Next Steps" in note.body
    assert (repository.notes_dir / "flying-cars.md").exists()


def test_body_override_replaces(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.create_from_template("meeting", "Custom Sync", body="My own body", token=raw, _store=store)
    assert out["success"] is True
    note = repository.read_note("custom-sync.md")
    assert note.body == "My own body"
    assert "## Attendees" not in note.body


def test_tags_union(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.create_from_template("meeting", "Tagged Sync", tags=["Q3", "MEETING"], token=raw, _store=store)
    assert out["success"] is True
    assert out["tags"] == ["meeting", "Q3"]
    assert repository.read_note("tagged-sync.md").metadata.tags == ["meeting", "Q3"]


@pytest.mark.parametrize("bad_name", ["sprint", "", "MEETING!"])
def test_unknown_template(token_store, read_write_token_pair, bad_name):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.create_from_template(bad_name, "X", token=raw, _store=store)
    assert out["success"] is False
    assert "Unknown template" in out["message"]
    assert "book" in out["message"]
    assert "idea" in out["message"]
    assert "meeting" in out["message"]


def test_template_name_case_insensitive_stripped(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.create_from_template("  Meeting ", "Case Test", token=raw, _store=store)
    assert out["success"] is True
    assert out["filename"] == "case-test"


def test_exists_reject(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    first = write_tools.create_from_template("meeting", "Dup Template", body="original", token=raw, _store=store)
    assert first["success"] is True
    second = write_tools.create_from_template("meeting", "Dup Template", body="overwrite", token=raw, _store=store)
    assert second["success"] is False
    assert "already exists" in second["message"]
    assert repository.read_note("dup-template.md").body == "original"


@pytest.mark.parametrize("bad", ["", "   "])
def test_invalid_title(token_store, read_write_token_pair, bad):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.create_from_template("meeting", bad, token=raw, _store=store)
    assert out["success"] is False
    assert "title" in out["message"]


@pytest.mark.parametrize("bad_tags", ["notalist", [123], ["x" * 100], ["ok", "   "]])
def test_invalid_tags(token_store, read_write_token_pair, bad_tags):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.create_from_template("meeting", "Taggy", tags=bad_tags, token=raw, _store=store)
    assert out["success"] is False
    assert "tags" in out["message"]


def test_invalid_created(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.create_from_template("meeting", "Dated", created="not-a-date", token=raw, _store=store)
    assert out["success"] is False
    assert "created" in out["message"]


def test_invalid_body(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.create_from_template("meeting", "Body Bad", body=123, token=raw, _store=store)
    assert out["success"] is False
    assert "body" in out["message"]


def test_unslugifiable_title(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.create_from_template("meeting", "!!!", token=raw, _store=store)
    assert out["success"] is False
    assert "title" in out["message"]


def test_created_default_and_explicit(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    default = write_tools.create_from_template("idea", "Default Date", token=raw, _store=store)
    assert default["success"] is True
    assert default["created"] == datetime.date.today().isoformat()
    explicit = write_tools.create_from_template(
        "idea", "Explicit Date", created="2026-01-15", token=raw, _store=store
    )
    assert explicit["success"] is True
    assert explicit["created"] == "2026-01-15"


def test_template_auth_denied(token_store, read_token_pair):
    read_raw, _ = read_token_pair
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        write_tools.create_from_template("meeting", "Hi", token="bogus", _store=token_store)
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        write_tools.create_from_template("meeting", "Hi", token=None, _store=token_store)
    with pytest.raises(AuthorizationError, match=WRITE_DENIED_MESSAGE.split(".")[0]):
        write_tools.create_from_template("meeting", "Hi", token=read_raw, _store=token_store)
    assert INVALID_TOKEN_MESSAGE.startswith("Invalid")
