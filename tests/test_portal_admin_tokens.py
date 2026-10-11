"""Admin token contract tests (11-02 task 3).

TestClient against mcp.http_app(), mirroring tests/test_portal_tokens.py:
monkeypatch portal_auth.validate_portal_jwt on BOTH the kb_mcp.portal_auth
module and the admin route module's portal_auth reference. Token store is a
real TokenStore on an isolated tmp_path file (no network); token_requests
helpers are stubbed per test (no network).
"""

import json

import pytest
from starlette.testclient import TestClient

from kb_mcp import portal_auth
from kb_mcp.portal_auth import (
    PORTAL_FORBIDDEN_MESSAGE,
    PORTAL_INVALID_MESSAGE,
    PortalUser,
)

ADMIN = PortalUser(id="u-admin", email="admin@example.com", is_admin=True)
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
    yield


@pytest.fixture()
def store(tmp_path):
    from kb_mcp.auth import TokenStore

    return TokenStore(store_path=tmp_path / ".tokens.json")


@pytest.fixture(autouse=True)
def _patch_store(monkeypatch, store):
    import kb_mcp.backend as backend
    import kb_mcp.portal_admin_token_routes as aroutes

    monkeypatch.setattr(backend, "get_token_store", lambda: store)
    monkeypatch.setattr(aroutes, "get_token_store", lambda: store)


def _login(monkeypatch, user=ADMIN):
    import kb_mcp.portal_admin_token_routes as aroutes

    monkeypatch.setattr(portal_auth, "validate_portal_jwt", lambda _t: user)
    monkeypatch.setattr(aroutes.portal_auth, "validate_portal_jwt", lambda _t: user)


def _deny_login(monkeypatch):
    import kb_mcp.portal_admin_token_routes as aroutes

    monkeypatch.setattr(portal_auth, "validate_portal_jwt", lambda _t: None)
    monkeypatch.setattr(aroutes.portal_auth, "validate_portal_jwt", lambda _t: None)


def _auth():
    return {"Authorization": "Bearer good-token"}


def _row(request_id, email, status="pending"):
    return {
        "id": request_id,
        "user_email": email,
        "status": status,
        "created_at": "2026-10-11T00:00:00+00:00",
        "decided_at": None,
        "decided_by": None,
    }


# --- queue -----------------------------------------------------------------

def test_queue_200_pending_oldest_first_history_below(client, monkeypatch):
    import kb_mcp.token_requests as requests_store

    _login(monkeypatch)
    pending = [_row(1, "a@example.com"), _row(2, "b@example.com")]
    history = [
        {**_row(3, "c@example.com", "denied"),
         "decided_at": "2026-10-11T01:00:00+00:00",
         "decided_by": ADMIN.email},
    ]
    monkeypatch.setattr(requests_store, "get_pending", lambda: pending)
    monkeypatch.setattr(requests_store, "get_decided", lambda limit=50: history)
    resp = client.get("/api/admin/requests", headers=_auth())
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert [r["id"] for r in body["pending"]] == [1, 2]
    assert body["history"][0]["status"] == "denied"
    assert body["pending"][0]["user_email"] == "a@example.com"


def test_queue_non_admin_403_no_rows_leaked(client, monkeypatch):
    _login(monkeypatch, user=USER)
    resp = client.get("/api/admin/requests", headers=_auth())
    assert resp.status_code == 403
    assert resp.json() == {"success": False, "message": PORTAL_FORBIDDEN_MESSAGE}
    assert "pending" not in json.dumps(resp.json())


def test_queue_forged_jwt_401_verbatim(client, monkeypatch):
    _deny_login(monkeypatch)
    resp = client.get("/api/admin/requests", headers=_auth())
    assert resp.status_code == 401
    assert resp.json() == {"success": False, "message": PORTAL_INVALID_MESSAGE}


# --- approve / deny ----------------------------------------------------------

def test_approve_200_mints_read_write_old_read_stays_valid(client, monkeypatch, store):
    import kb_mcp.token_requests as requests_store
    from kb_mcp.auth import TokenType

    _login(monkeypatch)
    old_raw, _ = store.add_token(
        username=USER.email, token_type=TokenType.READ,
        expires_at="2099-01-01T00:00:00+00:00")
    monkeypatch.setattr(requests_store, "get_pending", lambda: [_row(7, USER.email)])
    seen = {}

    def _decide(request_id, status, decided_by):
        seen.update(request_id=request_id, status=status, decided_by=decided_by)
        return {**_row(7, USER.email, status),
                "decided_at": "2026-10-11T02:00:00+00:00",
                "decided_by": decided_by}

    monkeypatch.setattr(requests_store, "set_decision", _decide)
    resp = client.post("/api/admin/requests/7/approve", json={}, headers=_auth())
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["token_type"] == "read_write"
    assert body["request_id"] == 7
    assert isinstance(body["token"], str) and len(body["token"]) >= 40
    assert seen == {"request_id": 7, "status": "approved", "decided_by": ADMIN.email}
    assert store.lookup(old_raw) is not None
    assert store.lookup(body["token"]) is not None


def test_approve_non_pending_409(client, monkeypatch):
    import kb_mcp.token_requests as requests_store

    _login(monkeypatch)
    monkeypatch.setattr(requests_store, "get_pending", lambda: [])
    resp = client.post("/api/admin/requests/999/approve", json={}, headers=_auth())
    assert resp.status_code == 409
    assert "no longer pending" in resp.json()["message"]


def test_approve_never_expire_write_400(client, monkeypatch):
    import kb_mcp.token_requests as requests_store

    _login(monkeypatch)
    monkeypatch.setattr(requests_store, "get_pending", lambda: [_row(7, USER.email)])
    resp = client.post("/api/admin/requests/7/approve", json={"expires_at": None},
                       headers=_auth())
    assert resp.status_code == 400
    assert "expiry" in resp.json()["message"].lower()


def test_deny_200_decided_at_no_reason_field(client, monkeypatch):
    import kb_mcp.token_requests as requests_store

    _login(monkeypatch)
    monkeypatch.setattr(requests_store, "get_pending", lambda: [_row(8, USER.email)])

    def _decide(request_id, status, decided_by):
        return {**_row(8, USER.email, status),
                "decided_at": "2026-10-11T03:00:00+00:00",
                "decided_by": decided_by}

    monkeypatch.setattr(requests_store, "set_decision", _decide)
    resp = client.post("/api/admin/requests/8/deny", json={}, headers=_auth())
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["status"] == "denied"
    assert body["decided_at"] == "2026-10-11T03:00:00+00:00"
    assert "reason" not in json.dumps(body)


# --- direct mint -------------------------------------------------------------

def test_direct_mint_read_and_read_write_for_any_email(client, monkeypatch):
    _login(monkeypatch)
    for token_type in ("read", "read_write"):
        resp = client.post("/api/admin/mint",
                           json={"email": "newhire@example.com", "token_type": token_type},
                           headers=_auth())
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == token_type
        assert body["username"] == "newhire@example.com"
        assert isinstance(body["token"], str) and len(body["token"]) >= 40


def test_direct_mint_invalid_type_400(client, monkeypatch):
    _login(monkeypatch)
    resp = client.post("/api/admin/mint",
                       json={"email": "x@example.com", "token_type": "owner"},
                       headers=_auth())
    assert resp.status_code == 400


# --- all-tokens / revoke / rotate --------------------------------------------

def test_all_tokens_shows_owner_emails_masked(client, monkeypatch, store):
    from kb_mcp.auth import TokenType

    _login(monkeypatch)
    store.add_token(username="a@example.com", token_type=TokenType.READ,
                    expires_at="2099-01-01T00:00:00+00:00")
    store.add_token(username="b@example.com", token_type=TokenType.READ_WRITE,
                    expires_at="2099-01-01T00:00:00+00:00")
    resp = client.get("/api/admin/tokens", headers=_auth())
    assert resp.status_code == 200
    tokens = resp.json()["tokens"]
    assert len(tokens) == 2
    owners = {t["username"] for t in tokens}
    assert owners == {"a@example.com", "b@example.com"}
    dump = json.dumps(resp.json())
    assert "token" not in resp.json()["tokens"][0]
    assert all(t["display"].endswith(t["suffix"]) for t in tokens)


def test_admin_revoke_any_token_lookup_fails_closed(client, monkeypatch, store):
    from kb_mcp.auth import TokenType

    _login(monkeypatch)
    raw, _ = store.add_token(username=USER.email, token_type=TokenType.READ,
                             expires_at="2099-01-01T00:00:00+00:00")
    assert store.lookup(raw) is not None
    resp = client.post("/api/admin/revoke", json={"id_or_prefix": raw[:8]},
                       headers=_auth())
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"
    assert store.lookup(raw) is None


def test_admin_rotate_returns_new_token_once(client, monkeypatch, store):
    from kb_mcp.auth import TokenType

    _login(monkeypatch)
    old_raw, _ = store.add_token(username=USER.email, token_type=TokenType.READ_WRITE,
                                 expires_at="2099-01-01T00:00:00+00:00")
    resp = client.post("/api/admin/rotate", json={"id_or_prefix": old_raw[:8]},
                       headers=_auth())
    assert resp.status_code == 200
    new_raw = resp.json()["token"]
    assert isinstance(new_raw, str) and len(new_raw) >= 40
    assert new_raw != old_raw
    assert store.lookup(old_raw) is None
    assert store.lookup(new_raw) is not None


def test_secrecy_proof_queue_and_lists_carry_no_raw_secret(client, monkeypatch, store):
    import kb_mcp.token_requests as requests_store
    from kb_mcp.auth import TokenType

    _login(monkeypatch)
    raw, _ = store.add_token(username=USER.email, token_type=TokenType.READ,
                             expires_at="2099-01-01T00:00:00+00:00")
    assert len(raw) >= 40
    monkeypatch.setattr(requests_store, "get_pending", lambda: [_row(1, USER.email)])
    monkeypatch.setattr(requests_store, "get_decided", lambda limit=50: [])
    queue_dump = json.dumps(client.get("/api/admin/requests", headers=_auth()).json())
    list_dump = json.dumps(client.get("/api/admin/tokens", headers=_auth()).json())
    assert raw not in queue_dump
    assert raw not in list_dump
