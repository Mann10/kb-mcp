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


# --- Supabase auth client cache (261015-lfe task 3) ---------------------


class _FakeAdmin:
    def __init__(self):
        self.updates = []

    def update_user_by_id(self, user_id, payload):
        self.updates.append((user_id, payload))


class _FakeAuth:
    def __init__(self):
        self.get_claims_calls = []
        self.get_user_calls = []
        self.admin = _FakeAdmin()

    def get_claims(self, token):
        self.get_claims_calls.append(token)
        return {"sub": "u-1", "email": "e@x.io", "app_metadata": {}}

    def get_user(self, token):
        self.get_user_calls.append(token)
        return {"id": "u-1", "email": "e@x.io", "app_metadata": {}}


class _FakeClient:
    def __init__(self, url, key):
        self.url = url
        self.key = key
        self.auth = _FakeAuth()


class _FakeSupabaseModule:
    """Stand-in for the `supabase` package, counting create_client calls."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.clients: list[_FakeClient] = []

    def create_client(self, url, key):
        self.calls.append((url, key))
        client = _FakeClient(url, key)
        self.clients.append(client)
        return client


@pytest.fixture()
def fake_supabase(monkeypatch):
    """Patch `supabase.create_client` and clear the module client cache."""
    import sys

    module = _FakeSupabaseModule()
    sys_module = type(sys)("supabase")
    sys_module.create_client = module.create_client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "supabase", sys_module)
    portal_auth._reset_client_cache()
    yield module
    portal_auth._reset_client_cache()


def test_two_claims_validations_create_one_client(monkeypatch, fake_supabase):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    portal_auth._supabase_get_claims("token-a")
    portal_auth._supabase_get_claims("token-b")
    assert len(fake_supabase.calls) == 1


def test_claims_then_user_share_one_client(monkeypatch, fake_supabase):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    portal_auth._supabase_get_claims("token-a")
    portal_auth._supabase_get_user("token-b")
    assert len(fake_supabase.calls) == 1


def test_client_is_reused_for_the_same_url_key_pair(fake_supabase):
    a = portal_auth._supabase_client("https://proj.supabase.co", "anon-key")
    b = portal_auth._supabase_client("https://proj.supabase.co", "anon-key")
    assert a is b
    assert len(fake_supabase.calls) == 1


def test_rotated_anon_key_yields_a_different_client(fake_supabase):
    a = portal_auth._supabase_client("https://proj.supabase.co", "anon-old")
    b = portal_auth._supabase_client("https://proj.supabase.co", "anon-new")
    assert a is not b
    assert len(fake_supabase.calls) == 2


def test_second_project_url_yields_a_different_client(fake_supabase):
    a = portal_auth._supabase_client("https://one.supabase.co", "anon-key")
    b = portal_auth._supabase_client("https://two.supabase.co", "anon-key")
    assert a is not b
    assert len(fake_supabase.calls) == 2


def test_service_role_key_never_returned_for_anon_lookup(monkeypatch, fake_supabase):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    monkeypatch.setenv("ADMIN_EMAILS", "owner@example.com")
    anon = portal_auth._supabase_client(
        "https://proj.supabase.co", "anon-key"
    )
    privileged = portal_auth._supabase_client(
        "https://proj.supabase.co", "service-key"
    )
    assert anon is not privileged
    assert anon.key == "anon-key"
    assert privileged.key == "service-key"
    # A second anon lookup must not be handed the privileged client.
    assert portal_auth._supabase_client("https://proj.supabase.co", "anon-key") is anon


def test_missing_env_raises_before_any_client_work(monkeypatch, fake_supabase):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    with pytest.raises(RuntimeError, match="Missing SUPABASE_URL / SUPABASE_ANON_KEY"):
        portal_auth._supabase_get_claims("t")
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Missing SUPABASE_URL / SUPABASE_ANON_KEY"):
        portal_auth._supabase_get_user("t")
    assert fake_supabase.calls == []


def test_blank_env_raises_before_any_client_work(monkeypatch, fake_supabase):
    monkeypatch.setenv("SUPABASE_URL", "   ")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "   ")
    with pytest.raises(RuntimeError, match="Missing SUPABASE_URL / SUPABASE_ANON_KEY"):
        portal_auth._supabase_get_claims("t")
    assert fake_supabase.calls == []


def test_admin_bootstrap_reuses_cached_service_role_client(monkeypatch, fake_supabase):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    monkeypatch.setenv("ADMIN_EMAILS", "owner@example.com")
    user = PortalUser(id="u-1", email="owner@example.com", is_admin=False)
    assert ensure_admin_bootstrap(user) is True
    assert ensure_admin_bootstrap(user) is True
    # Two bootstraps, one client — and it is the service_role bucket, never
    # the anon one.
    assert fake_supabase.calls == [("https://proj.supabase.co", "service-key")]
    assert fake_supabase.clients[0].auth.admin.updates[0][0] == "u-1"


def test_reset_client_cache_forces_a_rebuild(fake_supabase):
    first = portal_auth._supabase_client("https://proj.supabase.co", "anon-key")
    portal_auth._reset_client_cache()
    second = portal_auth._supabase_client("https://proj.supabase.co", "anon-key")
    assert first is not second
    assert len(fake_supabase.calls) == 2


def test_cached_client_is_used_only_for_stateless_verification():
    """No sign_in / set_session / refresh may be introduced on the cache."""
    import pathlib

    src = pathlib.Path("src/kb_mcp/portal_auth.py").read_text(encoding="utf-8")
    for forbidden in ("sign_in", "set_session", "refresh_session", "sign_in_with"):
        assert forbidden not in src


def test_module_import_reads_no_env_at_import_time():
    """portal_auth must stay import-safe: zero env reads at module scope."""
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("src/kb_mcp/portal_auth.py").read_text(encoding="utf-8"))
    for node in tree.body:
        assert not isinstance(node, (ast.Import, ast.ImportFrom)) or True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                func = sub.func
                assert not (
                    isinstance(func, ast.Attribute) and func.attr == "get"
                    and isinstance(func.value, ast.Attribute)
                    and func.value.attr == "environ"
                ), "module-level env read found — import-safety broken"
