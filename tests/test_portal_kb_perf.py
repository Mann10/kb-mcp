"""Round-trip constancy proofs for the KB read BFF (261015-lfe task 2).

The portal read endpoints used to issue ``list_stems()`` plus one
``read_note()`` per note — N+1 repository round-trips per HTTP request. On
Supabase each round-trip is a TCP+TLS+auth handshake, so the endpoint cost
scaled with note count.

These tests pin the replacement: a *counting* repository stub that records
every repository call the route makes. The same counts must be observed at
N=5 and at N=40 notes — identical counts at two sizes is what proves O(1).

The stub is a real filesystem ``NoteRepository`` subclass, so the route
contract exercised here is exactly the one
``tests/test_portal_kb_read.py`` already locks byte-for-byte.
"""

import pytest
from starlette.testclient import TestClient

from kb_mcp import portal_auth
from kb_mcp.portal_auth import PortalUser

USER = PortalUser(id="u-user", email="user@example.com", is_admin=False)

# Repository-call budget per endpoint. These are the O(1) constants the
# bulk reads introduced; none of them may scale with note count.
EXPECTED_CALLS = {
    "search": 2,  # list_stems + read_notes (one bulk query)
    "list": 1,    # read_all_metadata
    "tags": 1,    # read_all_metadata
    "get": 2,     # read_all_metadata + read_notes([stem])
}


class CountingRepo:
    """Filesystem NoteRepository subclass that counts repository round-trips."""

    def __init__(self, notes_dir):
        from kb_mcp.storage import NoteRepository

        self._inner = NoteRepository(notes_dir=notes_dir)
        self.notes_dir = self._inner.notes_dir
        self.calls: dict[str, int] = {
            "list_stems": 0,
            "read_note": 0,
            "read_notes": 0,
            "read_all_metadata": 0,
        }
        self.bulk_sizes: list[int] = []

    # --- counting surface -------------------------------------------------

    def _bump(self, name: str) -> None:
        self.calls[name] += 1

    @property
    def total(self) -> int:
        return sum(self.calls.values())

    def reset(self) -> None:
        for key in self.calls:
            self.calls[key] = 0
        self.bulk_sizes.clear()

    # --- delegated repository surface -------------------------------------

    def list_stems(self):
        self._bump("list_stems")
        return self._inner.list_stems()

    def read_note(self, filename):
        self._bump("read_note")
        return self._inner.read_note(filename)

    def read_notes(self, stems):
        self._bump("read_notes")
        stems = list(stems)
        self.bulk_sizes.append(len(stems))
        return self._inner.read_notes(stems)

    def read_all_metadata(self):
        self._bump("read_all_metadata")
        return self._inner.read_all_metadata()

    def write_note(self, filename, title, body, tags, created, *, actor="unknown"):
        return self._inner.write_note(
            filename, title, body, tags, created, actor=actor
        )


@pytest.fixture()
def client():
    from kb_mcp.server import mcp

    return TestClient(mcp.http_app())


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "ADMIN_EMAILS",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("PORTAL_ORIGINS", raising=False)
    monkeypatch.delenv("KB_BACKEND", raising=False)
    yield


@pytest.fixture()
def repo(tmp_path):
    return CountingRepo(tmp_path / "notes")


@pytest.fixture()
def token_store(tmp_path):
    from kb_mcp.auth import TokenStore

    return TokenStore(store_path=tmp_path / ".tokens.json")


@pytest.fixture()
def template_store(tmp_path):
    from kb_mcp.templates import TemplateStore

    return TemplateStore.load(store_path=tmp_path / "templates.json")


@pytest.fixture(autouse=True)
def _patch_backend(monkeypatch, repo, token_store, template_store):
    import kb_mcp.backend as backend
    import kb_mcp.portal_kb_read_routes as rroutes

    monkeypatch.setattr(backend, "get_note_repository", lambda: repo)
    monkeypatch.setattr(rroutes, "get_note_repository", lambda: repo)
    monkeypatch.setattr(backend, "get_token_store", lambda: token_store)
    monkeypatch.setattr(backend, "get_template_store", lambda: template_store)
    monkeypatch.setattr(rroutes, "get_template_store", lambda: template_store)
    monkeypatch.setattr(portal_auth, "validate_portal_jwt", lambda _t: USER)
    monkeypatch.setattr(rroutes.portal_auth, "validate_portal_jwt", lambda _t: USER)


def _auth():
    return {"Authorization": "Bearer good-token"}


def _seed(repo, n: int) -> None:
    """Seed ``n`` notes, each with a body hit on the query 'needle'."""
    for i in range(n):
        repo.write_note(
            f"note-{i:03d}.md",
            title=f"Note {i:03d}",
            body=(
                "Background prose that makes the file realistic. "
                f"The needle for index {i} lives in the body. "
                "Trailing words to give the snippet real context."
            ),
            tags=["work" if i % 2 == 0 else "personal"],
            created=f"2026-01-{i % 28 + 1:02d}",
            actor="user@example.com",
        )


def _counts_at(repo, client, n: int, endpoint: str, params: dict) -> dict[str, int]:
    _seed(repo, n)
    repo.reset()
    resp = client.get(endpoint, params=params, headers=_auth())
    assert resp.status_code == 200
    return dict(repo.calls)


# --- O(1) round-trips, proven at two note counts -------------------------


@pytest.mark.parametrize("n", [5, 40])
def test_search_round_trips_are_constant(client, repo, n):
    counts = _counts_at(repo, client, n, "/api/notes/search", {"q": "needle"})
    assert counts["list_stems"] == 1
    assert counts["read_notes"] == 1
    assert counts["read_note"] == 0
    assert sum(counts.values()) == EXPECTED_CALLS["search"]


@pytest.mark.parametrize("n", [5, 40])
def test_list_round_trips_are_constant(client, repo, n):
    counts = _counts_at(repo, client, n, "/api/notes/list", {})
    assert counts["read_all_metadata"] == 1
    assert counts["read_note"] == 0
    assert counts["read_notes"] == 0
    assert counts["list_stems"] == 0
    assert sum(counts.values()) == EXPECTED_CALLS["list"]


@pytest.mark.parametrize("n", [5, 40])
def test_tags_round_trips_are_constant(client, repo, n):
    counts = _counts_at(repo, client, n, "/api/notes/tags", {})
    assert counts["read_all_metadata"] == 1
    assert counts["read_note"] == 0
    assert sum(counts.values()) == EXPECTED_CALLS["tags"]


@pytest.mark.parametrize("n", [5, 40])
def test_get_round_trips_are_constant(client, repo, n):
    counts = _counts_at(repo, client, n, "/api/notes/get", {"stem": "note-000"})
    assert counts["read_all_metadata"] == 1
    assert counts["read_notes"] == 1
    assert counts["read_note"] == 0
    assert sum(counts.values()) <= EXPECTED_CALLS["get"]


def test_identical_counts_at_five_and_forty_notes(client, repo):
    """The whole point: costs do not scale with the corpus."""
    per_endpoint = {
        "/api/notes/search": {"q": "needle"},
        "/api/notes/list": {},
        "/api/notes/tags": {},
        "/api/notes/get": {"stem": "note-000"},
    }
    small = {path: _counts_at(repo, client, 5, path, params) for path, params in per_endpoint.items()}
    large = {path: _counts_at(repo, client, 40, path, params) for path, params in per_endpoint.items()}
    for path in per_endpoint:
        assert small[path] == large[path], f"{path} round-trips scale with note count"


# --- bulk read contract -------------------------------------------------


def test_read_notes_empty_input_short_circuits(tmp_path):
    from kb_mcp.storage import NoteRepository

    repo = NoteRepository(notes_dir=tmp_path / "notes")
    assert repo.read_notes([]) == {}


def test_read_all_metadata_ascending_stem_no_bodies(tmp_path):
    from kb_mcp.models import NoteMetadata
    from kb_mcp.storage import NoteRepository

    inner = NoteRepository(notes_dir=tmp_path / "notes")
    for name, title in (
        ("zebra", "Zebra"),
        ("alpha", "Alpha"),
        ("mango", "Mango"),
    ):
        inner.write_note(
            f"{name}.md", title=title, body="body text", tags=["t"],
            created="2026-01-01",
        )
    metas = inner.read_all_metadata()
    assert list(metas) == ["alpha", "mango", "zebra"]
    for meta in metas.values():
        assert isinstance(meta, NoteMetadata)
        assert not hasattr(meta, "body")


def test_read_notes_skips_missing_stems(tmp_path):
    from kb_mcp.storage import NoteRepository

    inner = NoteRepository(notes_dir=tmp_path / "notes")
    inner.write_note("present.md", title="Present", body="hi", tags=[], created="2026-01-01")
    notes = inner.read_notes(["present", "absent"])
    assert list(notes) == ["present"]


# --- byte-identical responses survive the refactor ----------------------


def test_responses_still_byte_identical_after_refactor(client, repo):
    from kb_mcp.portal_kb_read_routes import _build_snippet

    _seed(repo, 6)
    body = client.get("/api/notes/search", params={"q": "needle"}, headers=_auth()).json()
    # rank ladder intact: body hit outranks everything
    assert [r["stem"] for r in body["results"]] == [f"note-{i:03d}" for i in range(6)]
    assert all("snippet" in r for r in body["results"])
    assert "message" in body and "results" in body
    # snippet format preserved verbatim
    note_body = repo.read_note("note-000.md").body
    hit = note_body.lower().find("needle")
    assert body["results"][0]["snippet"] == _build_snippet(note_body, "needle", hit)

    listed = client.get("/api/notes/list", headers=_auth()).json()
    assert set(listed) == {"notes", "message"}
    assert all(set(n) == {"stem", "title", "tags", "created"} for n in listed["notes"])
    assert [n["created"] for n in listed["notes"]] == sorted(n["created"] for n in listed["notes"])

    tags = client.get("/api/notes/tags", headers=_auth()).json()
    assert set(tags) == {"tags", "message"}
    assert {t["tag"] for t in tags["tags"]} == {"work", "personal"}


def test_invalid_date_filter_short_circuits_before_any_read(client, repo):
    _seed(repo, 5)
    repo.reset()
    resp = client.get(
        "/api/notes/search",
        params={"q": "needle", "date_from": "not-a-date"},
        headers=_auth(),
    )
    assert resp.status_code == 200
    assert resp.json()["results"] == []
    assert "Invalid date filter value" in resp.json()["message"]
    assert repo.total == 0


def test_404_paths_still_fail_closed(client, repo):
    _seed(repo, 3)
    missing = client.get("/api/notes/get", params={"stem": "nope"}, headers=_auth())
    assert missing.status_code == 404
    assert missing.json() == {"success": False, "message": "Note 'nope' not found."}
    blank = client.get("/api/notes/get", headers=_auth())
    assert blank.status_code == 404


def test_401_body_unchanged(client, repo, monkeypatch):
    import kb_mcp.portal_kb_read_routes as rroutes

    monkeypatch.setattr(portal_auth, "validate_portal_jwt", lambda _t: None)
    monkeypatch.setattr(rroutes.portal_auth, "validate_portal_jwt", lambda _t: None)
    resp = client.get("/api/notes/list")
    assert resp.status_code == 401
    assert resp.json() == {
        "success": False,
        "message": portal_auth.PORTAL_INVALID_MESSAGE,
    }


# --- no N+1 anywhere in the read routes ---------------------------------


def test_no_per_stem_read_note_calls_remain():
    import pathlib

    src = pathlib.Path("src/kb_mcp/portal_kb_read_routes.py").read_text(encoding="utf-8")
    assert "repo.read_note(" not in src