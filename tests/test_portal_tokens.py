"""User self-serve token contract tests (11-01 task 3).

TestClient against mcp.http_app(), following tests/test_portal_routes.py
exactly: monkeypatch portal_auth.validate_portal_jwt on BOTH the
kb_mcp.portal_auth module and the route module's portal_auth reference.
Token store is a real TokenStore on an isolated tmp_path file (no network);
token_requests helpers are stubbed per test (no network).
"""

import json

import pytest
from starlette.testclient import TestClient

from kb_mcp import portal_auth
from kb_mcp.portal_auth import PORTAL_INVALID_MESSAGE, PortalUser

USER = PortalUser(id="u-user", email="user@example.com", is_admin=False)
OTHER = PortalUser(id="u-other", email="other@example.com", is_admin=False)


@pytest.fixture()
def client():
    from kb_mcp.server import mcp

    return TestClient(mcp.http_app())


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "ADMIN_EMAILS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("PORTAL_ORIGINS", raising=False)
    yield


@pytest.fixture()
def store(tmp_path):
    from kb_mcp.auth import TokenStore

    return TokenStore(store_path=tmp_path / ".tokens.json")


@pytest.fixture(autouse=True)
def _patch_store(monkeypatch, store):
    import kb_mcp.backend as backend
    import kb_mcp.portal_token_routes as troutes

    monkeypatch.setattr(backend, "get_token_store", lambda: store)
    monkeypatch.setattr(troutes, "get_token_store", lambda: store)


def _login(monkeypatch, user=USER):
    import kb_mcp.portal_token_routes as troutes

    monkeypatch.setattr(portal_auth, "validate_portal_jwt", lambda _t: user)
    monkeypatch.setattr(troutes.portal_auth, "validate_portal_jwt", lambda _t: user)


def _deny_login(monkeypatch):
    import kb_mcp.portal_token_routes as troutes

    monkeypatch.setattr(portal_auth, "validate_portal_jwt", lambda _t: None)
    monkeypatch.setattr(troutes.portal_auth, "validate_portal_jwt", lambda _t: None)


def _auth():
    return {"Authorization": "Bearer good-token"}


# --- mint-read -------------------------------------------------------------

def test_mint_read_200_carries_token_once(client, monkeypatch):
    _login(monkeypatch)
    resp = client.post("/api/tokens/mint-read", json={}, headers=_auth())
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert isinstance(body["token"], str) and len(body["token"]) >= 40
    assert body["prefix"] == body["token"][:8]
    assert body["token_type"] == "read"
    assert body["expires_at"] is not None


def test_mine_masks_no_raw_values(client, monkeypatch):
    _login(monkeypatch)
    minted = client.post("/api/tokens/mint-read", json={}, headers=_auth()).json()
    raw = minted["token"]
    resp = client.get("/api/tokens/mine", headers=_auth())
    assert resp.status_code == 200
    tokens = resp.json()["tokens"]
    assert len(tokens) == 1
    entry = tokens[0]
    assert "token" not in entry
    assert entry["display"] == f"{entry['prefix']}...{entry['suffix']}"
    assert entry["display"].endswith(entry["suffix"])
    assert entry["display"].startswith(entry["prefix"])
    assert entry["status"] == "active"
    assert raw not in json.dumps(resp.json())


def test_mint_cap_409_directs_to_revoke_or_rotate(client, monkeypatch, store):
    from kb_mcp.auth import TokenType

    _login(monkeypatch)
    for _ in range(5):
        store.add_token(username=USER.email, token_type=TokenType.READ,
                        expires_at="2099-01-01T00:00:00+00:00")
    resp = client.post("/api/tokens/mint-read", json={}, headers=_auth())
    assert resp.status_code == 409
    assert "Token limit reached" in resp.json()["message"]
    assert "Revoke or rotate" in resp.json()["message"]


def test_mint_never_expire_400(client, monkeypatch):
    _login(monkeypatch)
    resp = client.post("/api/tokens/mint-read", json={"expires_at": None},
                       headers=_auth())
    assert resp.status_code == 400
    assert "expiry" in resp.json()["message"].lower()


def test_forged_jwt_401_verbatim(client, monkeypatch):
    _deny_login(monkeypatch)
    resp = client.get("/api/tokens/mine", headers=_auth())
    assert resp.status_code == 401
    assert resp.json() == {"success": False, "message": PORTAL_INVALID_MESSAGE}


# --- write-upgrade request / cancel ----------------------------------------

def test_request_201(client, monkeypatch):
    import kb_mcp.token_requests as requests_store

    _login(monkeypatch)
    row = {"id": 1, "user_email": USER.email, "status": "pending",
           "created_at": "2026-10-11T00:00:00+00:00",
           "decided_at": None, "decided_by": None}
    monkeypatch.setattr(requests_store, "create_request", lambda _e: row)
    resp = client.post("/api/tokens/request", json={}, headers=_auth())
    assert resp.status_code == 201
    assert resp.json() == {"success": True, "request": row}


def test_request_duplicate_pending_409(client, monkeypatch):
    import kb_mcp.token_requests as requests_store

    _login(monkeypatch)
    monkeypatch.setattr(
        requests_store, "create_request",
        lambda _e: (_ for _ in ()).throw(
            requests_store.RequestConflict("pending exists")),
    )
    resp = client.post("/api/tokens/request", json={}, headers=_auth())
    assert resp.status_code == 409
    assert "already have a pending" in resp.json()["message"]


def test_my_request_shows_denied_with_decided_at(client, monkeypatch):
    import kb_mcp.token_requests as requests_store

    _login(monkeypatch)
    rows = [{"id": 3, "user_email": USER.email, "status": "denied",
             "created_at": "2026-10-11T00:00:00+00:00",
             "decided_at": "2026-10-11T01:00:00+00:00",
             "decided_by": "owner@example.com"}]
    monkeypatch.setattr(requests_store, "get_user_requests", lambda _e: rows)
    resp = client.get("/api/tokens/my-request", headers=_auth())
    assert resp.status_code == 200
    got = resp.json()["requests"]
    assert got[0]["status"] == "denied"
    assert got[0]["decided_at"] == "2026-10-11T01:00:00+00:00"
    assert "token" not in json.dumps(got)


def test_cancel_own_pending_200(client, monkeypatch):
    import kb_mcp.token_requests as requests_store

    _login(monkeypatch)
    deleted = {"id": 7, "user_email": USER.email, "status": "pending",
               "created_at": "2026-10-11T00:00:00+00:00",
               "decided_at": None, "decided_by": None}
    monkeypatch.setattr(requests_store, "cancel_request", lambda _i, _e: deleted)
    resp = client.request("DELETE", "/api/tokens/my-request", json={"id": 7},
                          headers=_auth())
    assert resp.status_code == 200
    assert resp.json() == {"success": True, "request": deleted}


def test_cancel_other_user_404(client, monkeypatch):
    import kb_mcp.token_requests as requests_store

    _login(monkeypatch)

    def _missing(_request_id, _email):
        raise KeyError("nope")

    monkeypatch.setattr(requests_store, "cancel_request", _missing)
    resp = client.request("DELETE", "/api/tokens/my-request", json={"id": 999},
                          headers=_auth())
    assert resp.status_code == 404
    assert resp.json()["message"] == "Request not found."


# --- revoke / rotate (TOK-06 own-token half) --------------------------------

def test_revoke_own_200_lookup_fails_closed(client, monkeypatch, store):
    _login(monkeypatch)
    raw = client.post("/api/tokens/mint-read", json={}, headers=_auth()).json()["token"]
    assert store.lookup(raw) is not None
    prefix = raw[:8]
    resp = client.post("/api/tokens/revoke", json={"id_or_prefix": prefix},
                       headers=_auth())
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"
    assert store.lookup(raw) is None


def test_rotate_returns_new_token_once_old_fails(client, monkeypatch, store):
    _login(monkeypatch)
    old_raw = client.post("/api/tokens/mint-read", json={}, headers=_auth()).json()["token"]
    resp = client.post("/api/tokens/rotate",
                       json={"id_or_prefix": old_raw[:8]}, headers=_auth())
    assert resp.status_code == 200
    new_raw = resp.json()["token"]
    assert isinstance(new_raw, str) and len(new_raw) >= 40
    assert new_raw != old_raw
    assert store.lookup(old_raw) is None
    assert store.lookup(new_raw) is not None


def test_secrecy_proof_lists_carry_no_raw_secret(client, monkeypatch):
    import kb_mcp.token_requests as requests_store

    _login(monkeypatch)
    raw = client.post("/api/tokens/mint-read", json={}, headers=_auth()).json()["token"]
    assert len(raw) >= 40
    monkeypatch.setattr(requests_store, "get_user_requests",
                        lambda _e: [{"id": 1, "user_email": USER.email,
                                     "status": "pending",
                                     "created_at": "2026-10-11T00:00:00+00:00",
                                     "decided_at": None, "decided_by": None}])
    mine_dump = json.dumps(client.get("/api/tokens/mine", headers=_auth()).json())
    mine_all_dump = json.dumps(
        client.get("/api/tokens/mine?include_revoked=1", headers=_auth()).json())
    req_dump = json.dumps(client.get("/api/tokens/my-request", headers=_auth()).json())
    assert raw not in mine_dump
    assert raw not in mine_all_dump
    assert raw not in req_dump
