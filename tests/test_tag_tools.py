"""WRITE-05/WRITE-06 proofs: add_tags + remove_tags over an isolated repo (no mocks)."""

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


def test_add_hit(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    created = write_tools.create_note("Tag Target", tags=["work"], token=raw, _store=store)
    assert created["success"] is True
    out = write_tools.add_tags("Tag Target", ["notes", "ideas"], token=raw, _store=store)
    assert out["success"] is True
    assert out["tags"] == ["work", "notes", "ideas"]
    assert out["filename"] == "tag-target"
    assert repository.read_note("tag-target.md").metadata.tags == ["work", "notes", "ideas"]


def test_add_idempotent_duplicate(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note("Tag Target", tags=["work"], token=raw, _store=store)
    dup = write_tools.add_tags("Tag Target", ["work"], token=raw, _store=store)
    assert dup["success"] is True
    assert "No changes" in dup["message"]
    case_dup = write_tools.add_tags("Tag Target", ["WORK"], token=raw, _store=store)
    assert case_dup["success"] is True
    assert "No changes" in case_dup["message"]
    write_tools.add_tags("Tag Target", ["notes"], token=raw, _store=store)
    in_list_dup = write_tools.add_tags("Tag Target", ["notes", "notes"], token=raw, _store=store)
    assert in_list_dup["success"] is True
    assert "No changes" in in_list_dup["message"]
    assert repository.read_note("tag-target.md").metadata.tags == ["work", "notes"]


def test_add_case_insensitive_existing_work(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note("Case Note", tags=["Work"], token=raw, _store=store)
    out = write_tools.add_tags("Case Note", ["work"], token=raw, _store=store)
    assert out["success"] is True
    assert "No changes" in out["message"]
    assert repository.read_note("case-note.md").metadata.tags == ["Work"]


def test_add_via_suffix_and_case(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note("Suffix Target", tags=["a"], token=raw, _store=store)
    via_suffix = write_tools.add_tags("suffix-target.md", ["b"], token=raw, _store=store)
    assert via_suffix["success"] is True
    assert via_suffix["tags"] == ["a", "b"]
    via_case = write_tools.add_tags("SUFFIX TARGET", ["c"], token=raw, _store=store)
    assert via_case["success"] is True
    assert repository.read_note("suffix-target.md").metadata.tags == ["a", "b", "c"]


def test_add_missing_note(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.add_tags("no-such-note", ["x"], token=raw, _store=store)
    assert out["success"] is False
    assert "not found" in out["message"]


@pytest.mark.parametrize("bad_tags", ["notalist", [123], ["x" * 100], ["ok", "   "]])
def test_add_invalid(token_store, read_write_token_pair, bad_tags):
    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note("Tag Target", tags=["work"], token=raw, _store=store)
    out = write_tools.add_tags("Tag Target", bad_tags, token=raw, _store=store)
    assert out["success"] is False
    assert "tags" in out["message"]


def test_remove_hit(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note(
        "Remove Target", tags=["work", "notes", "ideas"], token=raw, _store=store
    )
    out = write_tools.remove_tags("Remove Target", ["notes"], token=raw, _store=store)
    assert out["success"] is True
    assert out["tags"] == ["work", "ideas"]
    assert repository.read_note("remove-target.md").metadata.tags == ["work", "ideas"]


def test_remove_case_insensitive(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note("Case Remove", tags=["Work"], token=raw, _store=store)
    out = write_tools.remove_tags("Case Remove", ["work"], token=raw, _store=store)
    assert out["success"] is True
    assert out["tags"] == []
    assert repository.read_note("case-remove.md").metadata.tags == []


def test_remove_idempotent_missing(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note("Remove Target", tags=["work"], token=raw, _store=store)
    out = write_tools.remove_tags("Remove Target", ["nope"], token=raw, _store=store)
    assert out["success"] is True
    assert "No changes" in out["message"]
    assert repository.read_note("remove-target.md").metadata.tags == ["work"]


def test_remove_missing_note(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    out = write_tools.remove_tags("no-such-note", ["x"], token=raw, _store=store)
    assert out["success"] is False
    assert "not found" in out["message"]


@pytest.mark.parametrize("bad_tags", ["notalist", [123], ["x" * 100], ["ok", "   "]])
def test_remove_invalid(token_store, read_write_token_pair, bad_tags):
    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note("Remove Target", tags=["work"], token=raw, _store=store)
    out = write_tools.remove_tags("Remove Target", bad_tags, token=raw, _store=store)
    assert out["success"] is False
    assert "tags" in out["message"]


def test_tag_ops_single_commit(token_store, read_write_token_pair, repository):
    dulwich = pytest.importorskip("dulwich")
    from dulwich.repo import Repo

    raw, store = _w(token_store, read_write_token_pair)
    write_tools.create_note("Commit Tags", tags=["a"], token=raw, _store=store)

    def _commit_count():
        repo = Repo(str(repository.notes_dir))
        try:
            return len(list(repo.get_walker()))
        finally:
            repo.close()

    before = _commit_count()
    out = write_tools.add_tags("Commit Tags", ["b", "c"], token=raw, _store=store)
    assert out["success"] is True
    after = _commit_count()
    assert after - before == 1
    repo = Repo(str(repository.notes_dir))
    try:
        newest = next(iter(repo.get_walker())).commit.message.decode()
    finally:
        repo.close()
    assert newest.startswith("note(update)")

    before = _commit_count()
    rout = write_tools.remove_tags("Commit Tags", ["b"], token=raw, _store=store)
    assert rout["success"] is True
    after = _commit_count()
    assert after - before == 1


def test_add_auth_denied(token_store, read_token_pair):
    read_raw, _ = read_token_pair
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        write_tools.add_tags("Hi", ["x"], token="bogus", _store=token_store)
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        write_tools.add_tags("Hi", ["x"], token=None, _store=token_store)
    with pytest.raises(AuthorizationError, match=WRITE_DENIED_MESSAGE.split(".")[0]):
        write_tools.add_tags("Hi", ["x"], token=read_raw, _store=token_store)
    assert INVALID_TOKEN_MESSAGE.startswith("Invalid")


def test_remove_auth_denied(token_store, read_token_pair):
    read_raw, _ = read_token_pair
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        write_tools.remove_tags("Hi", ["x"], token="bogus", _store=token_store)
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        write_tools.remove_tags("Hi", ["x"], token=None, _store=token_store)
    with pytest.raises(AuthorizationError, match=WRITE_DENIED_MESSAGE.split(".")[0]):
        write_tools.remove_tags("Hi", ["x"], token=read_raw, _store=token_store)
