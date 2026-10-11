"""Fail-closed JWT + admin-gate proofs (10-01 task 1).

Hermetic: locally-signed HS256 fixtures + monkeypatched
_supabase_get_claims/_supabase_get_user. No network, no SUPABASE_URL required.
"""

import jwt
import pytest

from kb_mcp import portal_auth
from kb_mcp.portal_auth import (
    PortalUser,
    ensure_admin_bootstrap,
    is_admin_email,
    require_admin,
    require_user,
    validate_portal_jwt,
)

TEST_SECRET = "test-only-hs256-secret-0123456789"
WRONG_SECRET = "wrong-secret-for-forgery-probe-98765"


def _sign(payload: dict, secret: str = TEST_SECRET) -> str:
    return jwt.encode(payload, secret, algorithm="HS256")


def _valid_payload(**overrides) -> dict:
    base = {
        "sub": "user-123",
        "email": "User@Example.com",
        "app_metadata": {"is_admin": False},
    }
    base.update(overrides)
    return base


class _FakeHeaders(dict):
    def get(self, key, default=None):  # case-insensitive get
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default


class _FakeRequest:
    def __init__(self, auth_header: str | None):
        self.headers = _FakeHeaders()
        if auth_header is not None:
            self.headers["Authorization"] = auth_header


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "ADMIN_EMAILS",
    ):
        monkeypatch.delenv(var, raising=False)
    yield


def test_none_blank_missing_deny_fail_closed():
    assert validate_portal_jwt(None) is None
    assert validate_portal_jwt("") is None
    assert validate_portal_jwt("   ") is None
    assert validate_portal_jwt("Bearer    ") is None


def test_forged_hs256_denied(monkeypatch):
    forged = _sign(_valid_payload(), secret=WRONG_SECRET)

    def _boom_claims(_token):
        raise RuntimeError("invalid signature")

    def _boom_user(_token):
        raise RuntimeError("invalid token")

    monkeypatch.setattr(portal_auth, "_supabase_get_claims", _boom_claims)
    monkeypatch.setattr(portal_auth, "_supabase_get_user", _boom_user)
    assert validate_portal_jwt(forged) is None


def test_expired_token_denied(monkeypatch):
    import time

    expired = _sign({**_valid_payload(), "exp": int(time.time()) - 3600})

    def _boom_claims(_token):
        raise RuntimeError("token expired")

    def _boom_user(_token):
        raise RuntimeError("token expired")

    monkeypatch.setattr(portal_auth, "_supabase_get_claims", _boom_claims)
    monkeypatch.setattr(portal_auth, "_supabase_get_user", _boom_user)
    assert validate_portal_jwt(expired) is None


def test_client_sent_user_id_is_ignored():
    import pathlib

    src = pathlib.Path("src/kb_mcp/portal_auth.py").read_text(encoding="utf-8")
    assert "user_id" not in src
    # validate/require signatures take only raw/request — no user id param
    import inspect

    assert "user_id" not in inspect.signature(validate_portal_jwt).parameters
    assert "user_id" not in inspect.signature(require_user).parameters
    assert "user_id" not in inspect.signature(require_admin).parameters


def test_admin_emails_matching_case_insensitive(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", " Owner@Example.com , other@x.io ")
    assert is_admin_email("owner@example.com") is True
    assert is_admin_email("OWNER@EXAMPLE.COM") is True
    assert is_admin_email("  Owner@example.com ") is True
    assert is_admin_email("stranger@example.com") is False
    assert is_admin_email(None) is False
    assert is_admin_email("  ") is False


def test_bootstrap_failure_returns_false_without_raising(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "owner@example.com")
    # No SUPABASE_URL / SERVICE_ROLE set → must return False, not raise
    user = PortalUser(id="u-1", email="owner@example.com", is_admin=False)
    assert ensure_admin_bootstrap(user) is False
    # Non-listed email never attempts bootstrap
    outsider = PortalUser(id="u-2", email="stranger@example.com", is_admin=False)
    assert ensure_admin_bootstrap(outsider) is False


def test_valid_claims_primary_path(monkeypatch):
    monkeypatch.setattr(
        portal_auth,
        "_supabase_get_claims",
        lambda _t: {"sub": "u-9", "email": "a@b.io", "app_metadata": {"is_admin": True}},
    )
    user = validate_portal_jwt("any-token")
    assert user is not None
    assert user.id == "u-9"
    assert user.is_admin is True


def test_fallback_get_user_path(monkeypatch):
    def _raise(_t):
        raise RuntimeError("HS256 legacy — claims unavailable")

    monkeypatch.setattr(portal_auth, "_supabase_get_claims", _raise)
    monkeypatch.setattr(
        portal_auth,
        "_supabase_get_user",
        lambda _t: {"id": "u-7", "email": "f@b.io", "app_metadata": {}},
    )
    user = validate_portal_jwt("legacy-token")
    assert user is not None
    assert user.id == "u-7"
    assert user.is_admin is False


def test_require_user_reads_bearer_header(monkeypatch):
    monkeypatch.setattr(
        portal_auth,
        "_supabase_get_claims",
        lambda _t: {"sub": "u-1", "email": "e@x.io", "app_metadata": {}},
    )
    req = _FakeRequest("Bearer good-token")
    user = require_user(req)
    assert user is not None and user.id == "u-1"
    assert require_user(_FakeRequest(None)) is None
    assert require_user(_FakeRequest("Basic abc")) is None


def test_require_admin_denies_non_admin(monkeypatch):
    monkeypatch.setattr(
        portal_auth,
        "_supabase_get_claims",
        lambda _t: {"sub": "u-2", "email": "plain@x.io", "app_metadata": {}},
    )
    monkeypatch.setenv("ADMIN_EMAILS", "")
    assert require_admin(_FakeRequest("Bearer t")) is None


def test_service_role_only_via_env():
    import pathlib

    src = pathlib.Path("src/kb_mcp/portal_auth.py").read_text(encoding="utf-8")
    assert src.count("SUPABASE_SERVICE_ROLE_KEY") >= 1
    assert 'os.environ.get("SUPABASE_SERVICE_ROLE_KEY"' in src
    # No hardcoded secret literals: only the env-get line may mention the key name
    for line in src.splitlines():
        if "SUPABASE_SERVICE_ROLE_KEY" in line:
            assert "os.environ.get" in line
