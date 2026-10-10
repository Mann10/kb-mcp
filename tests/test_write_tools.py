"""WRITE-01/WRITE-04 proofs: create + delete over an isolated repo (no mocks)."""

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


def test_create_minimal_defaults(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.create_note("Hello World", token=raw, _store=store)
    assert out["success"] is True
    assert out["filename"] == "hello-world"
    assert (repository.notes_dir / "hello-world.md").exists()
    assert out["created"] == datetime.date.today().isoformat()


def test_create_full_echo(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.create_note(
        "Full Note",
        body="Some body",
        tags=["work", "notes"],
        created="2026-01-15",
        token=raw,
        _store=store,
    )
    assert out["success"] is True
    assert out["filename"] == "full-note"
    assert out["title"] == "Full Note"
    assert out["tags"] == ["work", "notes"]
    assert out["created"] == "2026-01-15"
    assert repository.read_note("full-note.md").body == "Some body"


def test_create_duplicate_rejected(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    first = write_tools.create_note("Dup Note", body="original", token=raw, _store=store)
    assert first["success"] is True
    second = write_tools.create_note("Dup Note", body="overwrite", token=raw, _store=store)
    assert second["success"] is False
    assert "already exists" in second["message"]
    assert repository.read_note("dup-note.md").body == "original"


@pytest.mark.parametrize("bad", ["", "   "])
def test_create_empty_title(token_store, read_write_token_pair, bad):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.create_note(bad, token=raw, _store=store)
    assert out["success"] is False
    assert "title" in out["message"]


@pytest.mark.parametrize("bad_tags", ["notalist", [123], ["x" * 100]])
def test_create_bad_tags(token_store, read_write_token_pair, bad_tags):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.create_note("Taggy", tags=bad_tags, token=raw, _store=store)
    assert out["success"] is False
    assert "tags" in out["message"]


@pytest.mark.parametrize("bad_date", ["not-a-date", "2026-13-01"])
def test_create_bad_date(token_store, read_write_token_pair, bad_date):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.create_note("Dated", created=bad_date, token=raw, _store=store)
    assert out["success"] is False
    assert "created" in out["message"]


def test_create_unslugifiable(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.create_note("!!!", token=raw, _store=store)
    assert out["success"] is False
    assert "title" in out["message"]


def test_delete_hit_and_variants(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    created = write_tools.create_note("Hello World", token=raw, _store=store)
    assert created["success"] is True
    out = write_tools.delete_note("Hello World", token=raw, _store=store)
    assert out["success"] is True
    assert out["filename"] == "hello-world"
    assert not (repository.notes_dir / "hello-world.md").exists()

    write_tools.create_note("Suffix Note", token=raw, _store=store)
    via_suffix = write_tools.delete_note("suffix-note.md", token=raw, _store=store)
    assert via_suffix["success"] is True
    assert via_suffix["filename"] == "suffix-note"

    write_tools.create_note("Case Note", token=raw, _store=store)
    via_case = write_tools.delete_note("CASE NOTE", token=raw, _store=store)
    assert via_case["success"] is True
    assert via_case["filename"] == "case-note"


def test_delete_missing(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.delete_note("no-such-note", token=raw, _store=store)
    assert out["success"] is False
    assert "not found" in out["message"]


def test_create_auth_denied(token_store, read_token_pair):
    read_raw, _ = read_token_pair
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        write_tools.create_note("Hi", token="bogus", _store=token_store)
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        write_tools.create_note("Hi", token=None, _store=token_store)
    with pytest.raises(AuthorizationError, match=WRITE_DENIED_MESSAGE.split(".")[0]):
        write_tools.create_note("Hi", token=read_raw, _store=token_store)
    assert INVALID_TOKEN_MESSAGE.startswith("Invalid")


def test_delete_auth_denied(token_store, read_token_pair):
    read_raw, _ = read_token_pair
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        write_tools.delete_note("Hi", token="bogus", _store=token_store)
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        write_tools.delete_note("Hi", token=None, _store=token_store)
    with pytest.raises(AuthorizationError, match=WRITE_DENIED_MESSAGE.split(".")[0]):
        write_tools.delete_note("Hi", token=read_raw, _store=token_store)
