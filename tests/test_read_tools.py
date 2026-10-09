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
        created="2026-01-02",
    )
    repository.write_note(
        "gamma-note.md",
        title="Gamma Report",
        body="grocery list and weekend ideas",
        tags=["personal"],
        created="2026-01-03",
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
