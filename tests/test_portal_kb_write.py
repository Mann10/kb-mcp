"""KB write BFF contract tests (12-02 task 2).

Level 1 write contract tests + Level 2 gate/rename/idempotency proofs over
Starlette TestClient against mcp.http_app(). Monkeypatches
portal_auth.validate_portal_jwt on BOTH the kb_mcp.portal_auth module and
the write-route module's portal_auth reference (never hits network). Notes
live in a real filesystem NoteRepository on tmp_path; the gate runs against
a real TokenStore seeded with read-only + read-write tokens.
"""

import pytest
from starlette.testclient import TestClient

from kb_mcp import portal_auth
from kb_mcp.portal_auth import PORTAL_INVALID_MESSAGE, PortalUser
from kb_mcp.portal_kb_write_routes import WRITE_DENIED

WRITER = PortalUser(id="u-writer", email="writer@example.com", is_admin=False)
READER = PortalUser(id="u-reader", email="reader@example.com", is_admin=False)


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
    import kb_mcp.portal_kb_write_routes as wroutes

    monkeypatch.setattr(backend, "get_note_repository", lambda: repo)
    monkeypatch.setattr(rroutes, "get_note_repository", lambda: repo)
    monkeypatch.setattr(wroutes, "get_note_repository", lambda: repo)
    monkeypatch.setattr(backend, "get_token_store", lambda: token_store)
    monkeypatch.setattr(backend, "get_template_store", lambda: template_store)
    monkeypatch.setattr(wroutes, "get_template_store", lambda: template_store)


@pytest.fixture(autouse=True)
def _seed_tokens(token_store):
    from kb_mcp.auth import TokenType

    token_store.add_token(
        username=WRITER.email, token_type=TokenType.READ_WRITE,
        expires_at="2099-01-01T00:00:00+00:00",
    )
    token_store.add_token(
        username=READER.email, token_type=TokenType.READ,
        expires_at="2099-01-01T00:00:00+00:00",
    )


def _login(monkeypatch, user=WRITER):
    import kb_mcp.portal_kb_write_routes as wroutes

    monkeypatch.setattr(portal_auth, "validate_portal_jwt", lambda _t: user)
    monkeypatch.setattr(wroutes.portal_auth, "validate_portal_jwt", lambda _t: user)


def _deny_login(monkeypatch):
    import kb_mcp.portal_kb_write_routes as wroutes

    monkeypatch.setattr(portal_auth, "validate_portal_jwt", lambda _t: None)
    monkeypatch.setattr(wroutes.portal_auth, "validate_portal_jwt", lambda _t: None)


def _auth():
    return {"Authorization": "Bearer good-token"}


# --- create ---------------------------------------------------------------

def test_create_happy_path(client, monkeypatch, repo):
    _login(monkeypatch)
    resp = client.post(
        "/api/notes/create",
        json={"title": "Hello World", "body": "first body", "tags": ["Work"], "created": "2026-05-01"},
        headers=_auth(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["note"]["stem"] == "hello-world"
    assert body["filename"] == "hello-world"
    assert repo.stem_exists("hello-world")


def test_create_exists_collision_409(client, monkeypatch, repo):
    _login(monkeypatch)
    payload = {"title": "Dup Note", "body": "b", "tags": [], "created": "2026-05-01"}
    assert client.post("/api/notes/create", json=payload, headers=_auth()).status_code == 200
    resp = client.post("/api/notes/create", json=payload, headers=_auth())
    assert resp.status_code == 409
    assert "already exists" in resp.json()["message"]


def test_create_empty_title_400(client, monkeypatch):
    _login(monkeypatch)
    resp = client.post("/api/notes/create", json={"title": "   "}, headers=_auth())
    assert resp.status_code == 400
    assert "Invalid title" in resp.json()["message"]


# --- create-from-template --------------------------------------------------

def test_create_from_template_meeting_prefill(client, monkeypatch, repo):
    _login(monkeypatch)
    resp = client.post(
        "/api/notes/create-from-template",
        json={"template": "meeting", "title": "Sync Notes"},
        headers=_auth(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "meeting" in body["message"]
    assert "meeting" in body["note"]["tags"]
    assert "Meeting Notes" in repo.read_note("sync-notes.md").body


def test_create_from_template_unknown_404_lists_valid(client, monkeypatch):
    _login(monkeypatch)
    resp = client.post(
        "/api/notes/create-from-template",
        json={"template": "nope", "title": "X"},
        headers=_auth(),
    )
    assert resp.status_code == 404
    message = resp.json()["message"]
    assert "Unknown template" in message
    assert "book" in message and "idea" in message and "meeting" in message


# --- update ---------------------------------------------------------------

def test_update_body_tags_happy_path(client, monkeypatch):
    _login(monkeypatch)
    client.post(
        "/api/notes/create",
        json={"title": "Updatable", "body": "old", "tags": ["a"], "created": "2026-05-01"},
        headers=_auth(),
    )
    resp = client.put(
        "/api/notes/update",
        json={"stem": "updatable", "body": "new", "tags": ["a", "b"]},
        headers=_auth(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["note"]["tags"] == ["a", "b"]
    assert body["new_stem"] == "updatable"


def test_update_title_rename_returns_new_stem(client, monkeypatch):
    _login(monkeypatch)
    client.post(
        "/api/notes/create",
        json={"title": "Old Title", "body": "b", "tags": [], "created": "2026-05-01"},
        headers=_auth(),
    )
    resp = client.put(
        "/api/notes/update", json={"stem": "old-title", "new_title": "New Title"}, headers=_auth()
    )
    assert resp.status_code == 200
    assert resp.json()["new_stem"] == "new-title"
    gone = client.get("/api/notes/get", params={"stem": "old-title"}, headers=_auth())
    assert gone.status_code == 404
    found = client.get("/api/notes/get", params={"stem": "new-title"}, headers=_auth())
    assert found.status_code == 200
    assert found.json()["note"]["title"] == "New Title"


def test_update_rename_target_exists_409(client, monkeypatch):
    _login(monkeypatch)
    client.post("/api/notes/create", json={"title": "Alpha", "body": "a"}, headers=_auth())
    client.post("/api/notes/create", json={"title": "Beta", "body": "b"}, headers=_auth())
    resp = client.put(
        "/api/notes/update", json={"stem": "alpha", "new_title": "Beta"}, headers=_auth()
    )
    assert resp.status_code == 409
    assert "Rename rejected" in resp.json()["message"]


def test_update_unknown_404(client, monkeypatch):
    _login(monkeypatch)
    resp = client.put("/api/notes/update", json={"stem": "ghost", "body": "x"}, headers=_auth())
    assert resp.status_code == 404
    assert "not found" in resp.json()["message"]


# --- delete ---------------------------------------------------------------

def test_delete_happy_path_and_unknown_404(client, monkeypatch):
    _login(monkeypatch)
    client.post("/api/notes/create", json={"title": "Temp Note", "body": "b"}, headers=_auth())
    resp = client.request("DELETE", "/api/notes/delete", json={"stem": "temp-note"}, headers=_auth())
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    again = client.request("DELETE", "/api/notes/delete", json={"stem": "temp-note"}, headers=_auth())
    assert again.status_code == 404
    assert "not found" in again.json()["message"]


# --- tags ------------------------------------------------------------------

def test_add_tags_idempotent_byte_identical_to_write_tools(client, monkeypatch):
    _login(monkeypatch)
    client.post(
        "/api/notes/create",
        json={"title": "Tagged", "body": "b", "tags": ["Work"], "created": "2026-05-01"},
        headers=_auth(),
    )
    first = client.post(
        "/api/notes/add-tags", json={"stem": "tagged", "tags": ["planning"]}, headers=_auth()
    )
    assert first.status_code == 200
    assert "Added 1 tag" in first.json()["message"]
    second = client.post(
        "/api/notes/add-tags", json={"stem": "tagged", "tags": [" Planning "]}, headers=_auth()
    )
    assert second.status_code == 200
    # Parity proof against the real gated tool with a write token:
    import kb_mcp.backend as backend
    import kb_mcp.write_tools as wt

    store = backend.get_token_store()
    wt.configure_default_repo(backend.get_note_repository())
    raw_token = _mint_raw_for(writer_email=WRITER.email, store=store)
    try:
        proof = wt.add_tags("tagged", [" Planning "], token=raw_token, _store=store)
    finally:
        wt.configure_default_repo(None)
    assert second.json()["message"] == proof["message"]
    assert "already has those tags" in second.json()["message"]


def _mint_raw_for(writer_email, store):
    """Mint a fresh raw token for parity-proof calls (returns the secret)."""
    from kb_mcp.auth import TokenType

    raw, _ = store.add_token(username=writer_email, token_type=TokenType.READ_WRITE)
    return raw


def test_remove_tags_idempotent(client, monkeypatch):
    _login(monkeypatch)
    client.post(
        "/api/notes/create",
        json={"title": "Untag", "body": "b", "tags": ["Work", "Old"], "created": "2026-05-01"},
        headers=_auth(),
    )
    resp = client.post(
        "/api/notes/remove-tags", json={"stem": "untag", "tags": ["old"]}, headers=_auth()
    )
    assert resp.status_code == 200
    assert resp.json()["note"]["tags"] == ["Work"]
    repeat = client.post(
        "/api/notes/remove-tags", json={"stem": "untag", "tags": ["OLD"]}, headers=_auth()
    )
    assert repeat.status_code == 200
    assert "already lacks those tags" in repeat.json()["message"]


def test_whitespace_only_tags_400(client, monkeypatch):
    _login(monkeypatch)
    client.post("/api/notes/create", json={"title": "WS Tags", "body": "b"}, headers=_auth())
    add = client.post(
        "/api/notes/add-tags", json={"stem": "ws-tags", "tags": ["   "]}, headers=_auth()
    )
    assert add.status_code == 400
    assert "Invalid tags" in add.json()["message"]
    remove = client.post(
        "/api/notes/remove-tags", json={"stem": "ws-tags", "tags": ["\t"]}, headers=_auth()
    )
    assert remove.status_code == 400
    assert "Invalid tags" in remove.json()["message"]


# --- auth gates ---------------------------------------------------------------

def test_forged_jwt_401_on_create(client, monkeypatch):
    _deny_login(monkeypatch)
    resp = client.post("/api/notes/create", json={"title": "X"}, headers=_auth())
    assert resp.status_code == 401
    assert resp.json() == {"success": False, "message": PORTAL_INVALID_MESSAGE}


def test_read_only_403_on_all_six_write_routes(client, monkeypatch):
    _login(monkeypatch, user=READER)
    probes = [
        ("POST", "/api/notes/create", {"title": "Denied"}),
        ("POST", "/api/notes/create-from-template", {"template": "meeting", "title": "Denied"}),
        ("PUT", "/api/notes/update", {"stem": "x", "body": "y"}),
        ("DELETE", "/api/notes/delete", {"stem": "x"}),
        ("POST", "/api/notes/add-tags", {"stem": "x", "tags": ["a"]}),
        ("POST", "/api/notes/remove-tags", {"stem": "x", "tags": ["a"]}),
    ]
    for method, path, payload in probes:
        resp = client.request(method, path, json=payload, headers=_auth())
        assert resp.status_code == 403, path
        assert resp.json() == {"success": False, "message": WRITE_DENIED}, path


# --- gate unit ---------------------------------------------------------------

def test_has_write_access_matrix(token_store):
    from kb_mcp.auth import TokenType
    from kb_mcp.portal_kb_gate import has_write_access
    import kb_mcp.backend as backend

    backend_get = backend.get_token_store
    backend.get_token_store = lambda: token_store
    try:
        assert has_write_access("writer@example.com") is True
        assert has_write_access("reader@example.com") is False
        raw_rev, entry_rev = token_store.add_token(
            username="revoked@example.com", token_type=TokenType.READ_WRITE
        )
        token_store.revoke_by_prefix(entry_rev.key_prefix)
        assert has_write_access("revoked@example.com") is False
        token_store.add_token(
            username="expired@example.com", token_type=TokenType.READ_WRITE,
            expires_at="2000-01-01T00:00:00+00:00",
        )
        assert has_write_access("expired@example.com") is False
        assert has_write_access("") is False
        assert has_write_access(None) is False
    finally:
        backend.get_token_store = backend_get
