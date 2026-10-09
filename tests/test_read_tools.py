"""READ-01/READ-02 proofs: search + get over a seeded repo (no mocks)."""

import pytest

from kb_mcp import read_tools
from kb_mcp.errors import AuthenticationError


@pytest.fixture
def seeded(repository):
    """Seed 3 valid notes + 1 malformed note; return the repository."""
    repository.write_note(
        "alpha-note.md",
        title="Alpha Note",
        body="orchestrator spawns planner for execution",
        tags=["work", "planning"],
        created="2026-01-01",
    )
    repository.write_note(
        "beta-note.md",
        title="Beta Note",
        body="checker verifies plans",
        tags=["Work", "review"],
        created="2026-02-01",
    )
    repository.write_note(
        "gamma-note.md",
        title="Gamma Report",
        body="grocery list and weekend ideas",
        tags=["personal"],
        created="2026-03-01",
    )
    (repository.notes_dir / "bad-note.md").write_text(
        "---\ntitle: [unclosed\n---\nbroken", encoding="utf-8"
    )
    return repository


@pytest.fixture(autouse=True)
def _use_seeded_repo(seeded):
    read_tools.configure_default_repo(seeded)
    yield
    read_tools.configure_default_repo(None)


def test_search_body_hit_snippet(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes("planner", token=raw, _store=token_store)
    filenames = [r["filename"] for r in out["results"]]
    assert "alpha-note" in filenames
    snippet = next(r["snippet"] for r in out["results"] if r["filename"] == "alpha-note")
    assert "planner" in snippet


def test_search_case_insensitive(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes("PLANNER", token=raw, _store=token_store)
    assert "alpha-note" in [r["filename"] for r in out["results"]]


def test_search_title_hit(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes("gamma", token=raw, _store=token_store)
    assert "gamma-note" in [r["filename"] for r in out["results"]]


def test_search_tags_hit(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes("review", token=raw, _store=token_store)
    assert "beta-note" in [r["filename"] for r in out["results"]]


def test_search_miss_payload(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes("zzz-no-such-thing", token=raw, _store=token_store)
    assert out["results"] == []
    assert "No notes" in out["message"]


def test_limit_clamp(token_store, read_token_pair):
    raw, _ = read_token_pair
    wide = read_tools.search_notes("e", limit=500, token=raw, _store=token_store)
    defaulted = read_tools.search_notes("e", limit=0, token=raw, _store=token_store)
    assert len(wide["results"]) <= 50
    assert len(defaulted["results"]) == len(wide["results"])


def test_malformed_note_skipped(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes("broken", token=raw, _store=token_store)
    assert out["results"] == []
    wide = read_tools.search_notes("e", token=raw, _store=token_store)
    assert "bad-note" not in [r["filename"] for r in wide["results"]]


def test_get_hit_fields(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.get_note("alpha-note", token=raw, _store=token_store)
    assert out["found"] is True
    assert out["filename"] == "alpha-note"
    assert out["title"] == "Alpha Note"
    assert out["tags"] == ["work", "planning"]
    assert out["created"] == "2026-01-01"
    assert "planner" in out["body"]


def test_get_case_variant(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.get_note("ALPHA-NOTE", token=raw, _store=token_store)
    assert out["found"] is True
    assert out["filename"] == "alpha-note"


def test_get_md_suffix(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.get_note("beta-note.md", token=raw, _store=token_store)
    assert out["found"] is True
    assert out["filename"] == "beta-note"


def test_get_missing_payload(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.get_note("nope", token=raw, _store=token_store)
    assert out["found"] is False  # structured miss: found is False
    assert "not found" in out["message"]


def test_search_auth_denied(token_store):
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        read_tools.search_notes("alpha", token="bogus", _store=token_store)
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        read_tools.search_notes("alpha", token=None, _store=token_store)


def test_get_auth_denied(token_store):
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        read_tools.get_note("alpha-note", token="bogus", _store=token_store)
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        read_tools.get_note("alpha-note", token=None, _store=token_store)


def test_list_returns_metadata_in_created_order(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.list_notes(token=raw, _store=token_store)
    assert [n["filename"] for n in out["notes"]] == [
        "alpha-note",
        "beta-note",
        "gamma-note",
    ]
    for entry in out["notes"]:
        assert set(entry.keys()) == {"filename", "title", "tags", "created"}
        assert "body" not in entry
    assert "Found 3 note(s)." in out["message"]


def test_list_empty_kb(token_store, read_token_pair, tmp_path):
    from kb_mcp.storage import NoteRepository

    empty = NoteRepository(notes_dir=tmp_path / "empty-notes")
    read_tools.configure_default_repo(empty)
    raw, _ = read_token_pair
    out = read_tools.list_notes(token=raw, _store=token_store)
    assert out["notes"] == []
    assert "No notes" in out["message"]


def test_get_tags_counts_and_order(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.get_tags(token=raw, _store=token_store)
    by_tag = {t["tag"]: t["count"] for t in out["tags"]}
    assert by_tag.get("work") == 2
    assert out["tags"][0] == {"tag": "work", "count": 2}
    assert sum(t["count"] for t in out["tags"]) >= 4
    assert "Found" in out["message"]


def test_get_tags_empty_kb(token_store, read_token_pair, tmp_path):
    from kb_mcp.storage import NoteRepository

    empty = NoteRepository(notes_dir=tmp_path / "empty-tags-notes")
    read_tools.configure_default_repo(empty)
    raw, _ = read_token_pair
    out = read_tools.get_tags(token=raw, _store=token_store)
    assert out["tags"] == []
    assert "No tags" in out["message"]


@pytest.mark.parametrize(
    "tool_name", ["search_notes", "get_note", "list_notes", "get_tags"]
)
def test_all_four_tools_deny_bogus_and_missing(token_store, tool_name):
    def invoke(extra):
        kwargs = dict(extra)
        kwargs["_store"] = token_store
        if tool_name == "search_notes":
            return read_tools.search_notes("x", **kwargs)
        if tool_name == "get_note":
            return read_tools.get_note("alpha-note", **kwargs)
        if tool_name == "list_notes":
            return read_tools.list_notes(**kwargs)
        return read_tools.get_tags(**kwargs)

    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        invoke({"token": "bogus"})
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        invoke({})


def test_list_revoked_token_denied(token_store, read_token_pair):
    raw, entry = read_token_pair
    token_store.revoke_by_prefix(entry.key_prefix[:4])
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        read_tools.list_notes(token=raw, _store=token_store)
