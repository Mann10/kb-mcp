"""Portal BFF custom routes (Phase 10-01 task 2).

Mounts auth-shell-only HTTP endpoints on the shared ``kb_mcp.server.mcp``
object via ``@mcp.custom_route`` (D-10, same Horizon process).

Import-safe: zero I/O and zero required env at import. All env reads
(SUPABASE_URL, PORTAL_ORIGINS, ...) happen per-request inside handlers
via :mod:`kb_mcp.portal_auth` or local helpers.
"""

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from kb_mcp import portal_auth
from kb_mcp.portal_auth import (
    PORTAL_FORBIDDEN_MESSAGE,
    PORTAL_INVALID_MESSAGE,
    require_admin,
    require_user,
)
from kb_mcp.portal_cors import _cors_headers, handle_options
from kb_mcp.server import mcp


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
