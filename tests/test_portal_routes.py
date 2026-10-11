"""Route-level 401/403/200 + CORS proofs (10-01 task 2).

Starlette TestClient against mcp.http_app(). Monkeypatches
portal_auth.validate_portal_jwt — never hits network.
"""

import pytest
from starlette.testclient import TestClient

from kb_mcp import portal_auth
from kb_mcp.portal_auth import (
    PORTAL_FORBIDDEN_MESSAGE,
    PORTAL_INVALID_MESSAGE,
    PortalUser,
)
from kb_mcp.server import mcp


@pytest.fixture()
def client():
    return TestClient(mcp.http_app())


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "ADMIN_EMAILS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("PORTAL_ORIGINS", raising=False)
    yield


def test_health_public_no_auth(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok", "service": "kb-mcp-portal"}


def test_me_without_header_401_verbatim(client, monkeypatch):
    monkeypatch.setattr(portal_auth, "validate_portal_jwt", lambda _t: None)
    # Also patch the reference imported into portal_routes
    import kb_mcp.portal_routes as routes

    monkeypatch.setattr(routes.portal_auth, "validate_portal_jwt", lambda _t: None)
    resp = client.get("/api/me")
    assert resp.status_code == 401
    assert resp.json() == {"success": False, "message": PORTAL_INVALID_MESSAGE}


def test_me_forged_jwt_401(client, monkeypatch):
    import kb_mcp.portal_routes as routes

    monkeypatch.setattr(portal_auth, "validate_portal_jwt", lambda _t: None)
    monkeypatch.setattr(routes.portal_auth, "validate_portal_jwt", lambda _t: None)
    resp = client.get("/api/me", headers={"Authorization": "Bearer forged-token-xyz"})
    assert resp.status_code == 401
    assert PORTAL_INVALID_MESSAGE in resp.json()["message"]


def test_admin_ping_non_admin_403_no_data_leak(client, monkeypatch):
    import kb_mcp.portal_routes as routes

    victim = PortalUser(id="u-plain", email="plain@example.com", is_admin=False)
    monkeypatch.setattr(portal_auth, "validate_portal_jwt", lambda _t: victim)
    monkeypatch.setattr(routes.portal_auth, "validate_portal_jwt", lambda _t: victim)
    monkeypatch.setattr(portal_auth, "ensure_admin_bootstrap", lambda _u: False)
    monkeypatch.setattr(routes.portal_auth, "ensure_admin_bootstrap", lambda _u: False)
    resp = client.get("/api/admin/ping", headers={"Authorization": "Bearer good-token"})
    assert resp.status_code == 403
    body = resp.json()
    assert body["success"] is False
    assert PORTAL_FORBIDDEN_MESSAGE in body["message"]
    assert "plain@example.com" not in resp.text


def test_admin_ping_admin_200(client, monkeypatch):
    import kb_mcp.portal_routes as routes

    admin = PortalUser(id="u-admin", email="owner@example.com", is_admin=True)
    monkeypatch.setattr(portal_auth, "validate_portal_jwt", lambda _t: admin)
    monkeypatch.setattr(routes.portal_auth, "validate_portal_jwt", lambda _t: admin)
    resp = client.get("/api/admin/ping", headers={"Authorization": "Bearer admin-token"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "email": "owner@example.com"}


def test_preflight_allowlisted_origin_echoes(client, monkeypatch):
    monkeypatch.setenv("PORTAL_ORIGINS", "https://app.vercel.app, http://localhost:5173")
    resp = client.options(
        "/api/me",
        headers={"Origin": "https://app.vercel.app", "Access-Control-Request-Method": "GET"},
    )
    assert resp.status_code == 204
    assert resp.headers.get("access-control-allow-origin") == "https://app.vercel.app"
    assert "GET" in resp.headers.get("access-control-allow-methods", "")


def test_preflight_non_allowlisted_origin_no_header(client, monkeypatch):
    monkeypatch.setenv("PORTAL_ORIGINS", "https://app.vercel.app")
    resp = client.options(
        "/api/me",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "GET"},
    )
    assert resp.status_code == 204
    assert "access-control-allow-origin" not in {k.lower(): v for k, v in resp.headers.items()}


def test_get_cors_echo_on_allowlisted_origin(client, monkeypatch):
    monkeypatch.setenv("PORTAL_ORIGINS", "https://app.vercel.app")
    resp = client.get("/api/health", headers={"Origin": "https://app.vercel.app"})
    assert resp.headers.get("access-control-allow-origin") == "https://app.vercel.app"
    resp2 = client.get("/api/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in {k.lower(): v for k, v in resp2.headers.items()}
