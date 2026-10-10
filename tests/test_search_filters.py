"""READ-05 proofs: tag filter + keyword-optional browse over isolated fixtures (no mocks)."""

import pytest

from kb_mcp import read_tools
from kb_mcp.errors import AuthenticationError


@pytest.fixture
def filter_seeded(repository):
    """Seed alpha/beta/gamma + homework-tagged delta + 1 malformed note."""
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
    repository.write_note(
        "delta-note.md",
        title="Delta Roster",
        body="housework roster and chores",
        tags=["homework"],
        created="2026-04-01",
    )
    (repository.notes_dir / "bad-note.md").write_text(
        "---\ntitle: [unclosed\n---\nbroken", encoding="utf-8"
    )
    return repository


@pytest.fixture(autouse=True)
def _use_filter_repo(filter_seeded):
    read_tools.configure_default_repo(filter_seeded)
    yield
    read_tools.configure_default_repo(None)


def test_tag_exact_match(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes("e", tag="work", token=raw, _store=token_store)
    assert {r["filename"] for r in out["results"]} == {"alpha-note", "beta-note"}


def test_tag_excludes_substring_homework(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes("", tag="work", token=raw, _store=token_store)
    assert "delta-note" not in [r["filename"] for r in out["results"]]
    assert "homework" not in [
        t for r in out["results"] for t in r["tags"] if t == "homework"
    ]


def test_tag_case_normalized(token_store, read_token_pair):
    raw, _ = read_token_pair
    lower = read_tools.search_notes("", tag="work", token=raw, _store=token_store)
    upper = read_tools.search_notes("", tag="Work", token=raw, _store=token_store)
    assert [r["filename"] for r in lower["results"]] == [
        r["filename"] for r in upper["results"]
    ]


def test_tag_single_hit(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes("", tag="planning", token=raw, _store=token_store)
    assert [r["filename"] for r in out["results"]] == ["alpha-note"]


def test_unknown_tag_structured_empty(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes("", tag="no-such-tag", token=raw, _store=token_store)
    assert out["results"] == []
    assert "no-such-tag" in out["message"]


def test_browse_by_tag_no_keyword(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes("", tag="personal", token=raw, _store=token_store)
    assert [r["filename"] for r in out["results"]] == ["gamma-note"]


def test_browse_created_order(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes("", tag="work", token=raw, _store=token_store)
    assert [r["filename"] for r in out["results"]] == ["alpha-note", "beta-note"]


def test_empty_query_no_filter_legacy(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes("", token=raw, _store=token_store)
    assert out["results"] == []
    assert "No notes" in out["message"]


def test_keyword_and_tag_narrowing(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes("planner", tag="review", token=raw, _store=token_store)
    assert out["results"] == []


def test_limit_respected_with_filter(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes("", tag="work", limit=1, token=raw, _store=token_store)
    assert len(out["results"]) == 1


def test_malformed_never_listed(token_store, read_token_pair):
    raw, _ = read_token_pair
    for kwargs in ({"tag": "work"}, {"tag": "personal"}, {}):
        if kwargs:
            out = read_tools.search_notes("", token=raw, _store=token_store, **kwargs)
        else:
            out = read_tools.search_notes("e", token=raw, _store=token_store)
        assert "bad-note" not in [r["filename"] for r in out["results"]]


def test_filtered_bogus_token_denied(token_store, read_token_pair):
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        read_tools.search_notes("", tag="work", token="bogus", _store=token_store)


def test_filtered_missing_token_denied(token_store, read_token_pair):
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        read_tools.search_notes("", tag="work", _store=token_store)


def test_date_both_bounds_inclusive(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes(
        "", date_from="2026-02-01", date_to="2026-03-01", token=raw, _store=token_store
    )
    assert [r["filename"] for r in out["results"]] == ["beta-note", "gamma-note"]


def test_date_single_day_boundary(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes(
        "", date_from="2026-02-01", date_to="2026-02-01", token=raw, _store=token_store
    )
    assert [r["filename"] for r in out["results"]] == ["beta-note"]


def test_date_only_start(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes(
        "", date_from="2026-03-01", token=raw, _store=token_store
    )
    assert [r["filename"] for r in out["results"]] == ["gamma-note", "delta-note"]


def test_date_only_end(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes(
        "", date_to="2026-01-01", token=raw, _store=token_store
    )
    assert [r["filename"] for r in out["results"]] == ["alpha-note"]


def test_date_out_of_range_structured_empty(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes(
        "", date_from="2030-01-01", token=raw, _store=token_store
    )
    assert out["results"] == []
    assert "2030-01-01" in out["message"]


def test_keyword_tag_date_and_combo(token_store, read_token_pair):
    raw, _ = read_token_pair
    hit = read_tools.search_notes(
        "checker",
        tag="review",
        date_from="2026-01-15",
        date_to="2026-02-15",
        token=raw,
        _store=token_store,
    )
    assert [r["filename"] for r in hit["results"]] == ["beta-note"]
    miss = read_tools.search_notes(
        "checker", tag="review", date_from="2026-03-01", token=raw, _store=token_store
    )
    assert miss["results"] == []


def test_keyword_date_combo_miss(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes(
        "planner", date_to="2025-12-31", token=raw, _store=token_store
    )
    assert out["results"] == []


def test_invalid_date_from_structured_empty(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes(
        "", date_from="not-a-date", token=raw, _store=token_store
    )
    assert out["results"] == []
    assert "not-a-date" in out["message"]
    assert "Invalid" in out["message"]


def test_invalid_date_to_structured_empty(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes(
        "", date_to="2024-13-99", token=raw, _store=token_store
    )
    assert out["results"] == []
    assert "2024-13-99" in out["message"]
    assert "Invalid" in out["message"]


def test_filter_echo_on_hit(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes(
        "gamma",
        tag="personal",
        date_from="2026-01-01",
        date_to="2026-12-31",
        token=raw,
        _store=token_store,
    )
    assert out["results"] != []
    assert "tag='personal'" in out["message"]
    assert "date_from='2026-01-01'" in out["message"]
    assert "date_to='2026-12-31'" in out["message"]


def test_filter_echo_on_miss(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes(
        "zzz", tag="personal", date_from="2026-01-01", token=raw, _store=token_store
    )
    assert out["results"] == []
    assert "tag='personal'" in out["message"]
    assert "date_from='2026-01-01'" in out["message"]


def test_unfiltered_legacy_message_identical(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes("planner", token=raw, _store=token_store)
    assert out["message"] == "Found 1 note(s) matching 'planner'."


def test_ranking_limit_with_date_filter(token_store, read_token_pair):
    raw, _ = read_token_pair
    out = read_tools.search_notes(
        "e", date_from="2026-01-01", limit=1, token=raw, _store=token_store
    )
    assert len(out["results"]) == 1
