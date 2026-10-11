"""Admin token BFF routes (Phase 11-02 task 1: queue + approve/deny).

Admin-gated endpoints mounted on the shared ``kb_mcp.server.mcp`` object via
``@mcp.custom_route`` (same Horizon process as portal_routes):

- ``GET /api/admin/requests`` — approval queue, pending oldest-first + history (D-09)
- ``POST /api/admin/requests/{request_id}/approve`` — approve mints a FRESH
  read-write token for the requester; old read token untouched (D-02, D-11)
- ``POST /api/admin/requests/{request_id}/deny`` — deny stamps decided_at;
  no denial-reason field in v3.0 (D-04)

Conventions (do not reshape): 401-vs-403 split (``require_user`` None → 401
``PORTAL_INVALID_MESSAGE``; user ok but not admin → 403
``PORTAL_FORBIDDEN_MESSAGE`` with zero rows leaked); CORS via
``portal_routes._cors_headers`` / ``handle_options``; structured
``{success:false, message}`` denials; raw secrets appear in exactly one
response field (``token`` on approve 200); masked-email logging only.

Import-safe: zero I/O and zero required env at import.
"""

import logging

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# NOTE: kb_mcp.server FIRST — it defines `mcp` before mounting portal_routes
# and portal_token_routes. Importing portal_routes/portal_token_routes before
# server leaves portal_routes partially initialized (circular import).
from kb_mcp.server import mcp
from kb_mcp import portal_auth
from kb_mcp import token_requests as requests_store
from kb_mcp.auth import TokenType
from kb_mcp.backend import get_token_store
from kb_mcp.portal_routes import _cors_headers, handle_options
from kb_mcp.portal_token_routes import _default_expiry

logger = logging.getLogger(__name__)

WRITE_EXPIRY_REQUIRED_MESSAGE = "Write tokens require an expiry."
NOT_PENDING_MESSAGE = "Request is no longer pending."


def _deny_401(request: Request) -> JSONResponse:
    """Fail-closed 401 with the locked portal message (T-11-06)."""
    return JSONResponse(
        {"success": False, "message": portal_auth.PORTAL_INVALID_MESSAGE},
        status_code=401,
        headers=_cors_headers(request),
    )


def _deny_403(request: Request) -> JSONResponse:
    """Message-only 403 with zero rows leaked (T-11-06)."""
    return JSONResponse(
        {"success": False, "message": portal_auth.PORTAL_FORBIDDEN_MESSAGE},
        status_code=403,
        headers=_cors_headers(request),
    )


def _gate_admin(request: Request):
    """401-vs-403 split gate. Returns (admin_user, None) or (None, response)."""
    user = portal_auth.require_user(request)
    if user is None:
        return None, _deny_401(request)
    admin = portal_auth.require_admin(request)
    if admin is None:
        logger.info(
            "admin route denied for %s", portal_auth.mask_email(user.email)
        )
        return None, _deny_403(request)
    return admin, None


def _find_pending(request_id) -> dict | None:
    """Locate a pending request by id (str-coerced; path params arrive as str)."""
    wanted = str(request_id)
    for row in requests_store.get_pending():
        if str(row.get("id")) == wanted:
            return row
    return None


@mcp.custom_route("/api/admin/requests", methods=["GET"])
async def admin_request_queue(request: Request) -> Response:
    """Approval queue: pending oldest-first on top, decided history below (D-09)."""
    _, denied = _gate_admin(request)
    if denied is not None:
        return denied
    pending = requests_store.get_pending()
    history = requests_store.get_decided(limit=50)
    return JSONResponse(
        {"success": True, "pending": pending, "history": history},
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/admin/requests/{request_id}/approve", methods=["POST"])
async def admin_request_approve(request: Request) -> Response:
    """Approve a pending request: stamp decision, mint a FRESH read-write token.

    The requester's old read token stays valid (D-02). Default TTL 90d unless
    the admin overrides per-mint (D-11); explicit null expiry is rejected (400).
    """
    admin, denied = _gate_admin(request)
    if denied is not None:
        return denied
    request_id = request.path_params.get("request_id")
    pending_row = _find_pending(request_id)
    if pending_row is None:
        return JSONResponse(
            {"success": False, "message": NOT_PENDING_MESSAGE},
            status_code=409,
            headers=_cors_headers(request),
        )
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    if "expires_at" in body and body["expires_at"] is None:
        return JSONResponse(
            {"success": False, "message": WRITE_EXPIRY_REQUIRED_MESSAGE},
            status_code=400,
            headers=_cors_headers(request),
        )
    expires_at = body.get("expires_at") or _default_expiry()
    decided = requests_store.set_decision(
        pending_row["id"], requests_store.STATUS_APPROVED, admin.email
    )
    store = get_token_store()
    raw, entry = store.add_token(
        username=pending_row["user_email"],
        token_type=TokenType.READ_WRITE,
        expires_at=expires_at,
    )
    logger.info(
        "write-upgrade approved for %s by %s prefix=%s...%s",
        portal_auth.mask_email(pending_row["user_email"]),
        portal_auth.mask_email(admin.email),
        entry.key_prefix,
        entry.key_suffix,
    )
    return JSONResponse(
        {
            "success": True,
            "token": raw,
            "prefix": entry.key_prefix,
            "token_type": TokenType.READ_WRITE.value,
            "expires_at": entry.expires_at,
            "request_id": decided["id"],
        },
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/admin/requests/{request_id}/approve", methods=["OPTIONS"])
async def admin_request_approve_options(request: Request) -> Response:
    """Preflight for approve (Horizon portability)."""
    return handle_options(request)


@mcp.custom_route("/api/admin/requests/{request_id}/deny", methods=["POST"])
async def admin_request_deny(request: Request) -> Response:
    """Deny a pending request: stamp decided_at/decided_by (D-04).

    No denial-reason field in v3.0 — the serializer carries status + timestamp.
    """
    admin, denied = _gate_admin(request)
    if denied is not None:
        return denied
    request_id = request.path_params.get("request_id")
    pending_row = _find_pending(request_id)
    if pending_row is None:
        return JSONResponse(
            {"success": False, "message": NOT_PENDING_MESSAGE},
            status_code=409,
            headers=_cors_headers(request),
        )
    decided = requests_store.set_decision(
        pending_row["id"], requests_store.STATUS_DENIED, admin.email
    )
    logger.info(
        "write-upgrade denied for %s by %s",
        portal_auth.mask_email(pending_row["user_email"]),
        portal_auth.mask_email(admin.email),
    )
    return JSONResponse(
        {
            "success": True,
            "status": decided["status"],
            "decided_at": decided["decided_at"],
            "request_id": decided["id"],
        },
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/admin/requests/{request_id}/deny", methods=["OPTIONS"])
async def admin_request_deny_options(request: Request) -> Response:
    """Preflight for deny (Horizon portability)."""
    return handle_options(request)
