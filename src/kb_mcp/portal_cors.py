"""Shared BFF CORS helpers (Phase 11 post-verification hardening).

Leaf module: imports only stdlib + starlette, never ``kb_mcp.server`` or any
route module. ``portal_routes``, ``portal_token_routes``, and
``portal_admin_token_routes`` all import from here so no import order can
leave a partially initialized module behind (cold
``import kb_mcp.portal_token_routes`` used to fail via the
portal_routes → server → admin → portal_routes cycle).
"""

import os

from starlette.requests import Request
from starlette.responses import Response


def _allowed_origins() -> list[str]:
    """Parse PORTAL_ORIGINS allowlist per-request (lowercased for compare)."""
    raw = os.environ.get("PORTAL_ORIGINS", "")
    if not raw.strip():
        return []
    return [o.strip().lower() for o in raw.split(",") if o.strip()]


def _echo_origin(request: Request) -> str | None:
    """Return the request Origin to echo, or None when not allowlisted."""
    try:
        origin = request.headers.get("origin")
    except Exception:
        return None
    if not origin or not origin.strip():
        return None
    allowed = _allowed_origins()
    if not allowed:
        return None
    if origin.strip().lower() in allowed:
        return origin.strip()
    return None


def _cors_headers(request: Request) -> dict[str, str]:
    """CORS headers for GET responses: echoed Allow-Origin when matched."""
    echoed = _echo_origin(request)
    if echoed:
        return {"Access-Control-Allow-Origin": echoed}
    return {}


def handle_options(request: Request) -> Response:
    """Shared OPTIONS/preflight helper: 204 + allowlist-echoed CORS headers."""
    headers: dict[str, str] = {
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Authorization, Content-Type",
    }
    echoed = _echo_origin(request)
    if echoed:
        headers["Access-Control-Allow-Origin"] = echoed
    return Response(status_code=204, headers=headers)
