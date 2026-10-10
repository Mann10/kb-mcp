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


def test_update_body(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    created = write_tools.create_note(
        "Update Me", body="Old body", tags=["a"], created="2026-02-01", token=raw, _store=store
    )
    assert created["success"] is True
    out = write_tools.update_note("Update Me", body="New body", token=raw, _store=store)
    assert out["success"] is True
    assert out["filename"] == "update-me"
    note = repository.read_note("update-me.md")
    assert note.body == "New body"
    assert note.metadata.title == "Update Me"
    assert note.metadata.tags == ["a"]
    assert note.metadata.created == "2026-02-01"


def test_update_tags_and_created(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note("Meta Note", body="B", tags=["x"], created="2026-01-01", token=raw, _store=store)
    out = write_tools.update_note(
        "Meta Note", tags=["y", "z"], created="2026-03-04", token=raw, _store=store
    )
    assert out["success"] is True
    assert out["tags"] == ["y", "z"]
    assert out["created"] == "2026-03-04"
    note = repository.read_note("meta-note.md")
    assert note.metadata.tags == ["y", "z"]
    assert note.metadata.created == "2026-03-04"
    assert note.body == "B"


def test_update_noop(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note("Noop Note", body="Same", token=raw, _store=store)
    before = (repository.notes_dir / "noop-note.md").read_text(encoding="utf-8-sig")
    out = write_tools.update_note("Noop Note", token=raw, _store=store)
    assert out["success"] is True
    assert "No changes" in out["message"]
    after = (repository.notes_dir / "noop-note.md").read_text(encoding="utf-8-sig")
    assert before == after


def test_update_noop_missing(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.update_note("no-such-note", token=raw, _store=store)
    assert out["success"] is False
    assert "not found" in out["message"]


def test_update_missing(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.update_note("no-such-note", body="x", token=raw, _store=store)
    assert out["success"] is False
    assert "not found" in out["message"]


@pytest.mark.parametrize("bad_tags", ["notalist", [123], ["x" * 100]])
def test_update_bad_tags(token_store, read_write_token_pair, repository, bad_tags):
    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note("Taggy Two", token=raw, _store=store)
    out = write_tools.update_note("Taggy Two", tags=bad_tags, token=raw, _store=store)
    assert out["success"] is False
    assert "tags" in out["message"]


@pytest.mark.parametrize("bad_date", ["not-a-date", "2026-13-01"])
def test_update_bad_date(token_store, read_write_token_pair, bad_date):
    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note("Dated Two", token=raw, _store=store)
    out = write_tools.update_note("Dated Two", created=bad_date, token=raw, _store=store)
    assert out["success"] is False
    assert "created" in out["message"]


@pytest.mark.parametrize("bad_title", ["", "   "])
def test_update_empty_new_title(token_store, read_write_token_pair, bad_title):
    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note("Rename Empty", token=raw, _store=store)
    out = write_tools.update_note("Rename Empty", new_title=bad_title, token=raw, _store=store)
    assert out["success"] is False
    assert "title" in out["message"]


def test_update_unslugifiable_new_title(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note("Rename Bang", token=raw, _store=store)
    out = write_tools.update_note("Rename Bang", new_title="!!!", token=raw, _store=store)
    assert out["success"] is False
    assert "title" in out["message"]


def test_update_bad_body(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note("Body Bad", token=raw, _store=store)
    out = write_tools.update_note("Body Bad", body=123, token=raw, _store=store)
    assert out["success"] is False
    assert "body" in out["message"]


def test_update_rename(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note("Old Title", body="Keep me", token=raw, _store=store)
    out = write_tools.update_note("Old Title", new_title="New Title", token=raw, _store=store)
    assert out["success"] is True
    assert out["filename"] == "new-title"
    assert not (repository.notes_dir / "old-title.md").exists()
    assert (repository.notes_dir / "new-title.md").exists()
    note = repository.read_note("new-title.md")
    assert note.metadata.title == "New Title"
    assert note.body == "Keep me"


def test_update_rename_collision(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note("Alpha Note", body="alpha-body", token=raw, _store=store)
    write_tools.create_note("Beta Note", body="beta-body", token=raw, _store=store)
    out = write_tools.update_note("Alpha Note", new_title="Beta Note", token=raw, _store=store)
    assert out["success"] is False
    assert "already exists" in out["message"]
    assert repository.read_note("alpha-note.md").body == "alpha-body"
    assert repository.read_note("beta-note.md").body == "beta-body"


def test_update_rename_plus_body_atomic(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note("Atomic Old", body="old", token=raw, _store=store)
    out = write_tools.update_note(
        "Atomic Old", new_title="Atomic New", body="new", token=raw, _store=store
    )
    assert out["success"] is True
    assert out["filename"] == "atomic-new"
    note = repository.read_note("atomic-new.md")
    assert note.metadata.title == "Atomic New"
    assert note.body == "new"
    assert not (repository.notes_dir / "atomic-old.md").exists()


def test_update_rename_single_commit(token_store, read_write_token_pair, repository):
    dulwich = pytest.importorskip("dulwich")
    from dulwich.repo import Repo

    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note("Commit Old", body="old", token=raw, _store=store)

    def _commit_count():
        repo = Repo(str(repository.notes_dir))
        try:
            return len(list(repo.get_walker()))
        finally:
            repo.close()

    before = _commit_count()
    out = write_tools.update_note(
        "Commit Old", new_title="Commit New", body="new", token=raw, _store=store
    )
    assert out["success"] is True
    after = _commit_count()
    assert after - before == 1
    repo = Repo(str(repository.notes_dir))
    try:
        newest = next(iter(repo.get_walker())).commit.message.decode()
    finally:
        repo.close()
    assert newest.startswith("note(update)")


def test_update_auth_denied(token_store, read_token_pair):
    read_raw, _ = read_token_pair
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        write_tools.update_note("Hi", body="x", token="bogus", _store=token_store)
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        write_tools.update_note("Hi", body="x", token=None, _store=token_store)
    with pytest.raises(AuthorizationError, match=WRITE_DENIED_MESSAGE.split(".")[0]):
        write_tools.update_note("Hi", body="x", token=read_raw, _store=token_store)
