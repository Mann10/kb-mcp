"""CORS preflight regressions (quick task 261016-ygc).

The bug these lock down: ``/api/notes/update`` is the only ``PUT`` route in the
portal BFF, but neither CORS layer advertised PUT. Starlette's CORSMiddleware
answers an unlisted method's preflight with a bare 400, which means the browser
never sends the PUT at all -- so a non-admin's attempt looked like a mysterious
"400 Bad Request" instead of the intended D-13 403 "Write access required.".

The two CORS layers are separate by design:

- ``serve()`` installs Starlette CORSMiddleware when fastmcp's ``run()``
  accepts a middleware kwarg.
- ``portal_cors.handle_options`` is the per-route fallback, and is the *only*
  CORS layer on the Horizon path where the middleware is skipped.

Both now share ``ALLOWED_METHODS``. The contract test below walks the real
route table and asserts every registered verb is advertised, so adding a route
with a new verb cannot silently reintroduce the drift.
"""

import sys

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient

from kb_mcp.portal_cors import ALLOWED_METHODS, handle_options

ORIGIN = "http://localhost:5173"


def _advertised(value: str) -> set[str]:
    return {m.strip().upper() for m in value.split(",") if m.strip()}


def _verbs(methods) -> set[str]:
    """Normalize a Starlette Route.methods (a set) to a comparable verb set.

    Starlette implicitly adds HEAD alongside GET. HEAD is served by the same
    allowlist entry as GET and browsers never send it in
    Access-Control-Request-Method, so it folds into GET here rather than
    forcing a meaningless HEAD entry into ALLOWED_METHODS.
    """
    if methods is None:
        return set()
    raw = {m.strip().upper() for m in methods if m and m.strip()}
    if "HEAD" in raw:
        raw.discard("HEAD")
        raw.add("GET")
    return raw


def _preflight(client, path, method, origin=ORIGIN):
    return client.request(
        "OPTIONS",
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


# --- The constant itself ------------------------------------------------


def test_allowed_methods_covers_every_http_verb_used_by_portal_routes():
    assert {"GET", "POST", "PUT", "DELETE", "OPTIONS"} <= _advertised(ALLOWED_METHODS)


def test_allowed_methods_parses_into_a_clean_list():
    """server.serve does ALLOWED_METHODS.split(', ') -- stray spaces would break it."""
    assert ALLOWED_METHODS.split(", ") == ["GET", "POST", "PUT", "DELETE", "OPTIONS"]


# --- Fallback layer: portal_cors.handle_options -------------------------


def test_handle_options_advertises_put():
    resp = handle_options(_FakeRequest(ORIGIN))
    assert "PUT" in _advertised(resp.headers["Access-Control-Allow-Methods"])


def test_handle_options_advertises_every_verb():
    resp = handle_options(_FakeRequest(ORIGIN))
    assert _advertised(resp.headers["Access-Control-Allow-Methods"]) == _advertised(ALLOWED_METHODS)


def test_handle_options_allows_authorization_header():
    resp = handle_options(_FakeRequest(ORIGIN))
    allow = resp.headers["Access-Control-Allow-Headers"]
    assert "authorization" in allow.lower()
    assert "content-type" in allow.lower()


def test_handle_options_echoes_allowlisted_origin(monkeypatch):
    monkeypatch.setenv("PORTAL_ORIGINS", ORIGIN)
    resp = handle_options(_FakeRequest(ORIGIN))
    assert resp.headers["Access-Control-Allow-Origin"] == ORIGIN


def test_handle_options_withholds_disallowed_origin(monkeypatch):
    monkeypatch.setenv("PORTAL_ORIGINS", ORIGIN)
    resp = handle_options(_FakeRequest("http://evil.example"))
    assert "Access-Control-Allow-Origin" not in resp.headers


def test_handle_options_omits_origin_header_when_env_unset(monkeypatch):
    """The unset-PORTAL_ORIGINS failure mode, at the fallback layer."""
    monkeypatch.delenv("PORTAL_ORIGINS", raising=False)
    resp = handle_options(_FakeRequest(ORIGIN))
    assert "Access-Control-Allow-Origin" not in resp.headers


def test_handle_options_is_204():
    assert handle_options(_FakeRequest(ORIGIN)).status_code == 204


# --- Middleware layer: what serve() actually installs -------------------


def _middleware_app():
    app = Starlette(
        routes=[Route("/api/notes/update", _put_route, methods=["PUT"])],
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=[ORIGIN],
                allow_methods=ALLOWED_METHODS.split(", "),
                allow_headers=["Authorization", "Content-Type"],
                max_age=600,
            )
        ],
    )
    return TestClient(app)


def _put_route(request):
    return Response("ok")


def test_middleware_preflight_accepts_put():
    """The exact 400 the user hit: PUT preflight against the middleware layer."""
    resp = _middleware_app().request(
        "OPTIONS",
        "/api/notes/update",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert resp.status_code < 400, f"PUT preflight was rejected with {resp.status_code}"
    assert "PUT" in resp.headers.get("Access-Control-Allow-Methods", "")


def test_middleware_preflight_accepts_every_verb():
    client = _middleware_app()
    for method in ("GET", "POST", "PUT", "DELETE"):
        resp = client.request(
            "OPTIONS",
            "/api/notes/update",
            headers={"Origin": ORIGIN, "Access-Control-Request-Method": method},
        )
        assert resp.status_code < 400, f"{method} preflight rejected with {resp.status_code}"


def test_middleware_still_rejects_unlisted_verb():
    """Guard against 'fix' by allowlisting everything."""
    resp = _middleware_app().request(
        "OPTIONS",
        "/api/notes/update",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "PATCH"},
    )
    assert resp.status_code == 400


def test_middleware_still_rejects_disallowed_origin():
    resp = _middleware_app().request(
        "OPTIONS",
        "/api/notes/update",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "PUT"},
    )
    assert resp.status_code == 400


def test_middleware_rejects_preflight_when_origin_allowlist_is_empty():
    """The silent-failure mode: unset PORTAL_ORIGINS -> every preflight 400s.

    This is why serve() now loads .env. Asserted here so the failure is at
    least visible if it ever comes back.
    """
    app = Starlette(
        routes=[Route("/api/notes/update", _put_route, methods=["PUT"])],
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=[],
                allow_methods=ALLOWED_METHODS.split(", "),
                allow_headers=["Authorization", "Content-Type"],
            )
        ],
    )
    resp = TestClient(app).request(
        "OPTIONS",
        "/api/notes/update",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "PUT"},
    )
    assert resp.status_code == 400


# --- Route table vs allowlist ------------------------------------------


def test_every_registered_route_verb_is_advertised():
    """Walk the real BFF route table; no verb may be missing from ALLOWED_METHODS.

    This is the drift guard. ``/api/notes/update`` registered PUT while the
    allowlist had only GET/POST/DELETE/OPTIONS, so this assertion is what would
    have caught it before it reached a browser.
    """
    import kb_mcp.server  # noqa: F401  (registers every custom_route)
    from kb_mcp.server import mcp

    advertised = _advertised(ALLOWED_METHODS)
    missing: dict[str, set[str]] = {}
    for route in mcp._get_additional_http_routes():
        gap = _verbs(getattr(route, "methods", None)) - advertised
        if gap:
            missing[route.path] = gap
    assert not missing, f"routes use verbs ALLOWED_METHODS does not advertise: {missing}"


def test_route_table_actually_contains_the_put_route():
    """Sanity: the drift guard above is meaningless if it walks zero routes."""
    import kb_mcp.server  # noqa: F401
    from kb_mcp.server import mcp

    routes = mcp._get_additional_http_routes()
    assert len(routes) > 20, "expected the full BFF route table to be registered"
    put_paths = {
        r.path for r in routes if "PUT" in _verbs(getattr(r, "methods", None))
    }
    assert "/api/notes/update" in put_paths, (
        "PUT /api/notes/update is the route this whole task is about; "
        "if it is gone, re-check that the guard still has a subject"
    )


# --- dotenv opt-in (quick task 261016-ygc) ----------------------------


def test_dotenv_load_is_off_by_default(monkeypatch):
    """serve() must not auto-load .env: it contaminates isolated launches."""
    from kb_mcp.server import _load_dotenv_best_effort

    monkeypatch.delenv("KB_MCP_LOAD_DOTENV", raising=False)
    called = []
    monkeypatch.setattr("dotenv.load_dotenv", lambda **kw: called.append(kw))
    assert _load_dotenv_best_effort() is False
    assert called == [], ".env was loaded without KB_MCP_LOAD_DOTENV"


@pytest.mark.parametrize("flag", ["1", "true", "TRUE", "yes", "on"])
def test_dotenv_load_runs_when_opted_in(monkeypatch, flag):
    from kb_mcp.server import _load_dotenv_best_effort

    monkeypatch.setenv("KB_MCP_LOAD_DOTENV", flag)
    called = []
    monkeypatch.setattr("dotenv.load_dotenv", lambda **kw: called.append(kw))
    assert _load_dotenv_best_effort() is True
    assert called == [{"override": False}], "must never override real env vars"


@pytest.mark.parametrize("flag", ["", "0", "false", "no", "off", "maybe"])
def test_dotenv_load_stays_off_for_falsey_flags(monkeypatch, flag):
    from kb_mcp.server import _load_dotenv_best_effort

    monkeypatch.setenv("KB_MCP_LOAD_DOTENV", flag)
    called = []
    monkeypatch.setattr("dotenv.load_dotenv", lambda **kw: called.append(kw))
    assert _load_dotenv_best_effort() is False
    assert called == []


def test_dotenv_load_survives_missing_dependency(monkeypatch):
    from kb_mcp.server import _load_dotenv_best_effort

    monkeypatch.setenv("KB_MCP_LOAD_DOTENV", "1")
    monkeypatch.setitem(sys.modules, "dotenv", None)  # forces ImportError
    assert _load_dotenv_best_effort() is False


class _FakeRequest:
    """Minimal stand-in for a Starlette Request (only .headers is read)."""

    def __init__(self, origin: str | None):
        self.headers = {"origin": origin} if origin else {}