"""KB read BFF contract tests (12-01 task 3).

Level 1 read contract tests + Level 2 parity proofs over Starlette
TestClient against mcp.http_app(). Monkeypatches
portal_auth.validate_portal_jwt on BOTH the kb_mcp.portal_auth module and
the read-route module's portal_auth reference (never hits network). Notes
live in a real filesystem NoteRepository on tmp_path; the token store is a
real TokenStore on an isolated tmp_path file.
"""

import pytest
from starlette.testclient import TestClient

from kb_mcp import portal_auth
from kb_mcp.portal_auth import PORTAL_INVALID_MESSAGE, PortalUser

USER = PortalUser(id="u-user", email="user@example.com", is_admin=False)


@pytest.fixture()
def client():
    from kb_mcp.server import mcp

    return TestClient(mcp.http_app())


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "ADMIN_EMAILS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("PORTAL_ORIGINS", raising=False)
    monkeypatch.delenv("KB_BACKEND", raising=False)
    yield


@pytest.fixture()
def repo(tmp_path):
    from kb_mcp.storage import NoteRepository

    return NoteRepository(notes_dir=tmp_path / "notes")


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


def _login(monkeypatch, user=USER):
    import kb_mcp.portal_kb_read_routes as rroutes

    monkeypatch.setattr(portal_auth, "validate_portal_jwt", lambda _t: user)
    monkeypatch.setattr(rroutes.portal_auth, "validate_portal_jwt", lambda _t: user)


def _deny_login(monkeypatch):
    import kb_mcp.portal_kb_read_routes as rroutes

    monkeypatch.setattr(portal_auth, "validate_portal_jwt", lambda _t: None)
    monkeypatch.setattr(rroutes.portal_auth, "validate_portal_jwt", lambda _t: None)


def _auth():
    return {"Authorization": "Bearer good-token"}


def _seed_rank_fixture(repo):
    """Body-hit + title-only + tags-only notes for the query 'planner'."""
    filler = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 6
    repo.write_note(
        "alpha-note.md",
        title="Alpha Note",
        body=f"{filler} the planner kicked off sprint work {filler}",
        tags=["work"],
        created="2026-01-01",
        actor="user@example.com",
    )
    repo.write_note(
        "planner-overview.md",
        title="Planner Overview",
        body="Quarterly goals and milestones without the keyword stem.",
        tags=["work"],
        created="2026-02-01",
        actor="user@example.com",
    )
    repo.write_note(
        "random.md",
        title="Random",
        body="Nothing relevant here at all.",
        tags=["planner-ops"],
        created="2026-03-01",
        actor="user@example.com",
    )


# --- search ---------------------------------------------------------------

def test_search_rank_order_body_title_tags_with_ellipsis(client, monkeypatch, repo):
    _login(monkeypatch)
    _seed_rank_fixture(repo)
    resp = client.get("/api/notes/search", params={"q": "planner"}, headers=_auth())
    assert resp.status_code == 200
    body = resp.json()
    stems = [r["stem"] for r in body["results"]]
    assert stems == ["alpha-note", "planner-overview", "random"]
    snippet = body["results"][0]["snippet"]
    assert "\u2026" in snippet
    assert "planner" in snippet.lower()


def test_search_empty_state_byte_identical_to_read_tools(client, monkeypatch, repo, token_store):
    from kb_mcp import read_tools
    from kb_mcp.auth import TokenType

    _login(monkeypatch)
    _seed_rank_fixture(repo)
    raw, _ = token_store.add_token(username=USER.email, token_type=TokenType.READ)
    resp = client.get("/api/notes/search", params={"q": "zzz-no-such-thing"}, headers=_auth())
    assert resp.status_code == 200
    expected = read_tools.search_notes("zzz-no-such-thing", token=raw, _store=token_store)
    assert resp.json()["message"] == expected["message"]
    assert resp.json()["results"] == []


def test_search_invalid_date_200_verbatim(client, monkeypatch, repo):
    _login(monkeypatch)
    _seed_rank_fixture(repo)
    resp = client.get(
        "/api/notes/search", params={"q": "planner", "date_from": "not-a-date"}, headers=_auth()
    )
    assert resp.status_code == 200
    assert "Invalid date filter value" in resp.json()["message"]
    assert "Use YYYY-MM-DD" in resp.json()["message"]


def test_search_tag_filter_normalized_exact(client, monkeypatch, repo):
    _login(monkeypatch)
    _seed_rank_fixture(repo)
    resp = client.get("/api/notes/search", params={"tag": "  Work "}, headers=_auth())
    assert resp.status_code == 200
    stems = {r["stem"] for r in resp.json()["results"]}
    assert stems == {"alpha-note", "planner-overview"}
    assert "tag='Work'" in resp.json()["message"]


def test_search_date_range_inclusive(client, monkeypatch, repo):
    _login(monkeypatch)
    _seed_rank_fixture(repo)
    resp = client.get(
        "/api/notes/search",
        params={"date_from": "2026-02-01", "date_to": "2026-02-01"},
        headers=_auth(),
    )
    assert resp.status_code == 200
    assert [r["stem"] for r in resp.json()["results"]] == ["planner-overview"]


def test_search_limit_default_10_max_50_clamp(client, monkeypatch, repo):
    _login(monkeypatch)
    for i in range(12):
        repo.write_note(
            f"bulk-{i:02d}.md",
            title=f"Bulk {i}",
            body="bulk body",
            tags=["bulk"],
            created=f"2026-04-{(i % 28) + 1:02d}",
            actor="user@example.com",
        )
    defaulted = client.get("/api/notes/search", params={"tag": "bulk"}, headers=_auth())
    assert len(defaulted.json()["results"]) == 10
    zero = client.get("/api/notes/search", params={"tag": "bulk", "limit": "0"}, headers=_auth())
    assert len(zero.json()["results"]) == 10
    clamped = client.get(
        "/api/notes/search", params={"tag": "bulk", "limit": "500"}, headers=_auth()
    )
    assert len(clamped.json()["results"]) == 12


def test_search_forged_jwt_401(client, monkeypatch, repo):
    _deny_login(monkeypatch)
    resp = client.get("/api/notes/search", params={"q": "planner"}, headers=_auth())
    assert resp.status_code == 401
    assert resp.json() == {"success": False, "message": PORTAL_INVALID_MESSAGE}


# --- list ------------------------------------------------------------------

def test_list_created_ascending_metadata_only(client, monkeypatch, repo):
    _login(monkeypatch)
    _seed_rank_fixture(repo)
    resp = client.get("/api/notes/list", headers=_auth())
    assert resp.status_code == 200
    body = resp.json()
    assert [n["stem"] for n in body["notes"]] == ["alpha-note", "planner-overview", "random"]
    for note in body["notes"]:
        assert "body" not in note
        assert set(note) == {"stem", "title", "tags", "created"}


# --- get -------------------------------------------------------------------

def test_get_by_stem_and_title_and_md_suffix(client, monkeypatch, repo):
    _login(monkeypatch)
    _seed_rank_fixture(repo)
    by_stem = client.get("/api/notes/get", params={"stem": "alpha-note"}, headers=_auth())
    assert by_stem.status_code == 200
    assert by_stem.json()["note"]["body"].startswith("Lorem ipsum")
    by_title = client.get(
        "/api/notes/get", params={"title": "Planner Overview"}, headers=_auth()
    )
    assert by_title.status_code == 200
    assert by_title.json()["note"]["stem"] == "planner-overview"
    by_suffix = client.get("/api/notes/get", params={"stem": "random.md"}, headers=_auth())
    assert by_suffix.status_code == 200
    assert by_suffix.json()["note"]["stem"] == "random"


def test_get_unknown_404_structured(client, monkeypatch, repo):
    _login(monkeypatch)
    _seed_rank_fixture(repo)
    resp = client.get("/api/notes/get", params={"stem": "nope"}, headers=_auth())
    assert resp.status_code == 404
    assert resp.json()["success"] is False
    assert "not found" in resp.json()["message"]


# --- tags ------------------------------------------------------------------

def test_tags_sorted_count_then_name(client, monkeypatch, repo):
    _login(monkeypatch)
    _seed_rank_fixture(repo)
    resp = client.get("/api/notes/tags", headers=_auth())
    assert resp.status_code == 200
    tags = resp.json()["tags"]
    assert tags[0] == {"tag": "work", "count": 2}
    assert {"tag": "planner-ops", "count": 1} in tags


# --- templates --------------------------------------------------------------

def test_templates_catalog_has_builtins(client, monkeypatch):
    _login(monkeypatch)
    resp = client.get("/api/notes/templates", headers=_auth())
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["templates"]}
    assert {"meeting", "book", "idea"} <= names
    for template in resp.json()["templates"]:
        assert set(template) == {"name", "body_skeleton", "default_tags"}


# --- can_write ---------------------------------------------------------------

def test_can_write_false_no_token_data_leak(client, monkeypatch):
    _login(monkeypatch)
    resp = client.get("/api/notes/can_write", headers=_auth())
    assert resp.status_code == 200
    assert resp.json() == {"can_write": False}
    assert "prefix" not in resp.text
    assert "token" not in resp.text.replace("can_write", "")


def test_can_write_true_with_active_write_token(client, monkeypatch, token_store):
    from kb_mcp.auth import TokenType

    writer = PortalUser(id="u-writer", email="writer@example.com", is_admin=False)
    _login(monkeypatch, user=writer)
    token_store.add_token(
        username="writer@example.com",
        token_type=TokenType.READ_WRITE,
        expires_at="2099-01-01T00:00:00+00:00",
    )
    resp = client.get("/api/notes/can_write", headers=_auth())
    assert resp.status_code == 200
    assert resp.json() == {"can_write": True}
