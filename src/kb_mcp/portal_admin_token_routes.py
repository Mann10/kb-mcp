"""Admin token BFF routes (Phase 11-02 task 1: queue + approve/deny).

Admin-gated endpoints mounted on the shared ``kb_mcp.server.mcp`` object via
``@mcp.custom_route`` (same Horizon process as portal_routes):

- ``GET /api/admin/requests`` — approval queue, pending oldest-first + history (D-09)
- ``POST /api/admin/requests/{request_id}/approve`` — approve mints a FRESH
  read-write token for the requester; old read token untouched (D-02, D-11)
- ``POST /api/admin/requests/{request_id}/deny`` — deny stamps decided_at;
  no extra text fields in v3.0 (D-04)

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
from kb_mcp.portal_token_routes import _default_expiry, _mask_entry, _sort_active_first

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

    v3.0 carries status + timestamp only in the response.
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


# --- Direct mint + all-tokens + admin lifecycle (task 2) ---------------------

_MINT_TYPES = {"read": TokenType.READ, "read_write": TokenType.READ_WRITE}


@mcp.custom_route("/api/admin/mint", methods=["POST"])
async def admin_mint(request: Request) -> Response:
    """Direct admin mint for any email with either type (D-10, TOK-05).

    Optional TTL override; explicit null expiry passes through (never-expire
    is admin-only per D-05). The reveal goes to the admin to pass on.
    """
    admin, denied = _gate_admin(request)
    if denied is not None:
        return denied
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    email = (body.get("email") or "").strip()
    token_type_raw = (body.get("token_type") or "").strip().lower()
    if not email or token_type_raw not in _MINT_TYPES:
        return JSONResponse(
            {
                "success": False,
                "message": "email and token_type ('read' or 'read_write') are required.",
            },
            status_code=400,
            headers=_cors_headers(request),
        )
    token_type = _MINT_TYPES[token_type_raw]
    expires_at = body.get("expires_at") if "expires_at" in body else _default_expiry()
    store = get_token_store()
    raw, entry = store.add_token(
        username=email, token_type=token_type, expires_at=expires_at
    )
    logger.info(
        "direct %s token minted for %s by %s prefix=%s...%s",
        token_type_raw,
        portal_auth.mask_email(email),
        portal_auth.mask_email(admin.email),
        entry.key_prefix,
        entry.key_suffix,
    )
    return JSONResponse(
        {
            "success": True,
            "token": raw,
            "prefix": entry.key_prefix,
            "token_type": token_type.value,
            "username": entry.username,
            "expires_at": entry.expires_at,
        },
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/admin/mint", methods=["OPTIONS"])
async def admin_mint_options(request: Request) -> Response:
    """Preflight for direct mint (Horizon portability)."""
    return handle_options(request)


@mcp.custom_route("/api/admin/tokens", methods=["GET"])
async def admin_token_list(request: Request) -> Response:
    """All tokens with owner email, masked; active-only default (D-13/D-15)."""
    _, denied = _gate_admin(request)
    if denied is not None:
        return denied
    params = request.query_params
    include_revoked = (params.get("include_revoked") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    store = get_token_store()
    masked = [_mask_entry(e) for e in store.list_entries(include_revoked_expired=True)]
    if not include_revoked:
        masked = [m for m in masked if m["status"] == "active"]
    return JSONResponse(
        {"success": True, "tokens": _sort_active_first(masked)},
        headers=_cors_headers(request),
    )


def _resolve_any_token(store, key: str):
    """Find any token by exact id (key_hash) or prefix — admin scope, no
    ownership check (T-11-08: admin acts on all tokens)."""
    for entry in store.list_entries(include_revoked_expired=True):
        if entry.key_hash == key or entry.key_prefix.startswith(key):
            return entry
    return None


@mcp.custom_route("/api/admin/revoke", methods=["POST"])
async def admin_revoke(request: Request) -> Response:
    """Revoke any token by id or prefix (D-12, TOK-06 admin parity)."""
    admin, denied = _gate_admin(request)
    if denied is not None:
        return denied
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    key = body.get("id_or_prefix") or body.get("id") or body.get("prefix")
    if not key or not str(key).strip():
        return JSONResponse(
            {"success": False, "message": "Token id is required."},
            status_code=400,
            headers=_cors_headers(request),
        )
    store = get_token_store()
    target = _resolve_any_token(store, str(key).strip())
    if target is None:
        return JSONResponse(
            {"success": False, "message": "Token not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    try:
        entry = store.revoke_by_prefix(target.key_prefix)
    except KeyError:
        return JSONResponse(
            {"success": False, "message": "Token not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    logger.info(
        "token %s...%s revoked by admin %s",
        entry.key_prefix,
        entry.key_suffix,
        portal_auth.mask_email(admin.email),
    )
    return JSONResponse(
        {"success": True, "status": "revoked", "prefix": entry.key_prefix},
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/admin/revoke", methods=["OPTIONS"])
async def admin_revoke_options(request: Request) -> Response:
    """Preflight for admin revoke (Horizon portability)."""
    return handle_options(request)


@mcp.custom_route("/api/admin/rotate", methods=["POST"])
async def admin_rotate(request: Request) -> Response:
    """Rotate any token: revoke old + mint new carrying identity/TTL (D-14)."""
    admin, denied = _gate_admin(request)
    if denied is not None:
        return denied
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    key = body.get("id_or_prefix") or body.get("id") or body.get("prefix")
    if not key or not str(key).strip():
        return JSONResponse(
            {"success": False, "message": "Token id is required."},
            status_code=400,
            headers=_cors_headers(request),
        )
    store = get_token_store()
    target = _resolve_any_token(store, str(key).strip())
    if target is None:
        return JSONResponse(
            {"success": False, "message": "Token not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    try:
        if "expires_at" in body:
            new_raw, new_entry = store.rotate_by_prefix(
                target.key_prefix, expires_at=body.get("expires_at")
            )
        else:
            new_raw, new_entry = store.rotate_by_prefix(target.key_prefix)
    except KeyError:
        return JSONResponse(
            {"success": False, "message": "Token not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    try:
        new_type = new_entry.token_type.value
    except AttributeError:
        new_type = str(new_entry.token_type)
    logger.info(
        "token %s...%s rotated by admin %s to %s...%s",
        target.key_prefix,
        target.key_suffix,
        portal_auth.mask_email(admin.email),
        new_entry.key_prefix,
        new_entry.key_suffix,
    )
    return JSONResponse(
        {
            "success": True,
            "token": new_raw,
            "prefix": new_entry.key_prefix,
            "token_type": new_type,
            "expires_at": new_entry.expires_at,
        },
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/admin/rotate", methods=["OPTIONS"])
async def admin_rotate_options(request: Request) -> Response:
    """Preflight for admin rotate (Horizon portability)."""
    return handle_options(request)
