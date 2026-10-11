"""Portal BFF custom routes (Phase 10-01 task 2).

Mounts auth-shell-only HTTP endpoints on the shared ``kb_mcp.server.mcp``
object via ``@mcp.custom_route`` (D-10, same Horizon process).

Import-safe: zero I/O and zero required env at import. All env reads
(SUPABASE_URL, PORTAL_ORIGINS, ...) happen per-request inside handlers
via :mod:`kb_mcp.portal_auth` or local helpers.
"""

import os

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from kb_mcp import portal_auth
from kb_mcp.portal_auth import (
    PORTAL_FORBIDDEN_MESSAGE,
    PORTAL_INVALID_MESSAGE,
    require_admin,
    require_user,
)
from kb_mcp.server import mcp


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


@mcp.custom_route("/api/health", methods=["GET"])
async def portal_health(request: Request) -> Response:
    """Public liveness probe — no auth (Horizon/liveness friendly)."""
    return JSONResponse(
        {"status": "ok", "service": "kb-mcp-portal"},
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/me", methods=["GET"])
async def portal_me(request: Request) -> Response:
    """Authenticated identity probe → {id, email, is_admin} or 401."""
    user = require_user(request)
    if user is None:
        return JSONResponse(
            {"success": False, "message": PORTAL_INVALID_MESSAGE},
            status_code=401,
            headers=_cors_headers(request),
        )
    return JSONResponse(
        {"id": user.id, "email": user.email, "is_admin": user.is_admin},
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/me", methods=["OPTIONS"])
async def portal_me_options(request: Request) -> Response:
    """Preflight for /api/me (Horizon portability — manual Origin echo)."""
    return handle_options(request)


@mcp.custom_route("/api/admin/ping", methods=["GET"])
async def portal_admin_ping(request: Request) -> Response:
    """Admin-gated placeholder: 200 {ok, email} or 401/403 message-only."""
    user = require_user(request)
    if user is None:
        return JSONResponse(
            {"success": False, "message": PORTAL_INVALID_MESSAGE},
            status_code=401,
            headers=_cors_headers(request),
        )
    admin = require_admin(request)
    if admin is None:
        return JSONResponse(
            {"success": False, "message": PORTAL_FORBIDDEN_MESSAGE},
            status_code=403,
            headers=_cors_headers(request),
        )
    return JSONResponse(
        {"ok": True, "email": admin.email},
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/admin/ping", methods=["OPTIONS"])
async def portal_admin_ping_options(request: Request) -> Response:
    """Preflight for /api/admin/ping (Horizon portability)."""
    return handle_options(request)
