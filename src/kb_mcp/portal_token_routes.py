"""User self-serve token BFF routes (Phase 11-01 task 2).

Seven user-gated endpoints mounted on the shared ``kb_mcp.server.mcp``
object via ``@mcp.custom_route`` (same Horizon process as portal_routes):

- ``POST /api/tokens/mint-read`` — self-serve read-only mint (D-05/D-06/D-08)
- ``GET /api/tokens/mine`` — own masked token list (D-13/D-15)
- ``POST /api/tokens/request`` — write-upgrade request (D-03)
- ``GET /api/tokens/my-request`` — own request history incl. denied (D-04)
- ``DELETE /api/tokens/my-request`` — cancel own pending request (D-03)
- ``POST /api/tokens/revoke`` — revoke own token (D-14, TOK-06 parity)
- ``POST /api/tokens/rotate`` — rotate own token, one-time reveal (D-14)

Conventions (do not reshape): fail-closed ``portal_auth.require_user`` gate
on every route; CORS via ``portal_routes._cors_headers`` / ``handle_options``;
structured ``{success:false, message}`` denials; raw secrets appear in exactly
one response field (``token`` on mint/rotate 200) and never in lists or logs.
Token ``username`` is stamped with the portal login email verbatim (D-07).

Import-safe: zero I/O and zero required env at import.
"""

import logging
from datetime import datetime, timedelta, timezone

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from kb_mcp import portal_auth
from kb_mcp import token_requests
from kb_mcp.auth import TokenType, token_status
from kb_mcp.backend import get_token_store
from kb_mcp.portal_routes import _cors_headers, handle_options
from kb_mcp.server import mcp

logger = logging.getLogger(__name__)

SELF_SERVE_CAP=5  # D-05 starting point: max active self-serve read tokens per user
SELF_SERVE_DEFAULT_TTL_DAYS=90  # D-05 starting point: default TTL prefilled, user-editable

_STATUS_RANK = {"active": 0, "expired": 1, "revoked": 2}


def _deny_401(request: Request) -> JSONResponse:
    """Fail-closed 401 with the locked portal message (T-11-01)."""
    return JSONResponse(
        {"success": False, "message": portal_auth.PORTAL_INVALID_MESSAGE},
        status_code=401,
        headers=_cors_headers(request),
    )


async def _read_json(request: Request) -> dict:
    """Parse a JSON body; ``{}`` on any failure (untrusted input, fail-closed)."""
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _mask_entry(entry) -> dict:
    """Masked operator view of a token (T-11-03): ``prefix...suffix`` only."""
    token_type = entry.token_type
    try:
        token_type = token_type.value
    except AttributeError:
        token_type = str(token_type)
    return {
        "prefix": entry.key_prefix,
        "suffix": entry.key_suffix,
        "display": f"{entry.key_prefix}...{entry.key_suffix}",
        "token_type": token_type,
        "username": entry.username,
        "created_at": entry.created_at,
        "expires_at": entry.expires_at,
        "status": token_status(entry),
    }


def _default_expiry() -> str:
    """Server-side default TTL for self-serve mints (D-05: 90 days)."""
    return (
        datetime.now(timezone.utc) + timedelta(days=SELF_SERVE_DEFAULT_TTL_DAYS)
    ).isoformat()


def _sort_active_first(rows: list[dict]) -> list[dict]:
    """Active tokens first, then expired, then revoked (D-15)."""
    return sorted(
        rows,
        key=lambda m: (_STATUS_RANK.get(m.get("status"), 3), m.get("created_at")),
    )


@mcp.custom_route("/api/tokens/mint-read", methods=["POST"])
async def tokens_mint_read(request: Request) -> Response:
    """Mint a read-only token for the logged-in user; secret revealed once."""
    user = portal_auth.require_user(request)
    if user is None:
        return _deny_401(request)
    body = await _read_json(request)
    if "expires_at" in body and body["expires_at"] is None:
        return JSONResponse(
            {
                "success": False,
                "message": "Self-serve tokens require an expiry "
                "(admin can mint never-expiring).",
            },
            status_code=400,
            headers=_cors_headers(request),
        )
    store = get_token_store()
    active_reads = [
        e
        for e in store.list_entries(include_revoked_expired=True)
        if e.username == user.email
        and e.token_type == TokenType.READ
        and token_status(e) == "active"
    ]
    if len(active_reads) >= SELF_SERVE_CAP:
        return JSONResponse(
            {
                "success": False,
                "message": f"Token limit reached ({SELF_SERVE_CAP} active). "
                "Revoke or rotate an old token first.",
            },
            status_code=409,
            headers=_cors_headers(request),
        )
    expires_at = body.get("expires_at") or _default_expiry()
    raw, entry = store.add_token(
        username=user.email, token_type=TokenType.READ, expires_at=expires_at
    )
    logger.info(
        "self-serve read token minted for %s prefix=%s...%s",
        portal_auth.mask_email(user.email),
        entry.key_prefix,
        entry.key_suffix,
    )
    return JSONResponse(
        {
            "success": True,
            "token": raw,
            "prefix": entry.key_prefix,
            "token_type": TokenType.READ.value,
            "expires_at": entry.expires_at,
        },
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/tokens/mint-read", methods=["OPTIONS"])
async def tokens_mint_read_options(request: Request) -> Response:
    """Preflight for /api/tokens/mint-read (Horizon portability)."""
    return handle_options(request)


@mcp.custom_route("/api/tokens/mine", methods=["GET"])
async def tokens_mine(request: Request) -> Response:
    """List the caller's own tokens, masked; active-only by default (D-13/D-15)."""
    user = portal_auth.require_user(request)
    if user is None:
        return _deny_401(request)
    params = request.query_params
    include_revoked = (params.get("include_revoked") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    store = get_token_store()
    own = [
        e
        for e in store.list_entries(include_revoked_expired=True)
        if e.username == user.email
    ]
    masked = [_mask_entry(e) for e in own]
    if not include_revoked:
        masked = [m for m in masked if m["status"] == "active"]
    return JSONResponse(
        {"success": True, "tokens": _sort_active_first(masked)},
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/tokens/request", methods=["POST"])
async def tokens_request(request: Request) -> Response:
    """Request a write upgrade; one pending max per user (D-03)."""
    user = portal_auth.require_user(request)
    if user is None:
        return _deny_401(request)
    try:
        created = token_requests.create_request(user.email)
    except token_requests.RequestConflict:
        return JSONResponse(
            {
                "success": False,
                "message": "You already have a pending request. "
                "Cancel it before requesting again.",
            },
            status_code=409,
            headers=_cors_headers(request),
        )
    logger.info(
        "write-upgrade requested by %s",
        portal_auth.mask_email(user.email),
    )
    return JSONResponse(
        {"success": True, "request": created},
        status_code=201,
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/tokens/request", methods=["OPTIONS"])
async def tokens_request_options(request: Request) -> Response:
    """Preflight for /api/tokens/request (Horizon portability)."""
    return handle_options(request)


@mcp.custom_route("/api/tokens/my-request", methods=["GET"])
async def tokens_my_request(request: Request) -> Response:
    """Own write-upgrade requests incl. decided_at; denied stays visible (D-04)."""
    user = portal_auth.require_user(request)
    if user is None:
        return _deny_401(request)
    rows = token_requests.get_user_requests(user.email)
    return JSONResponse(
        {"success": True, "requests": rows},
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/tokens/my-request", methods=["DELETE"])
async def tokens_my_request_cancel(request: Request) -> Response:
    """Cancel the caller's own pending request (D-03)."""
    user = portal_auth.require_user(request)
    if user is None:
        return _deny_401(request)
    body = await _read_json(request)
    request_id = body.get("id")
    if request_id is None:
        return JSONResponse(
            {"success": False, "message": "Request id is required."},
            status_code=400,
            headers=_cors_headers(request),
        )
    try:
        deleted = token_requests.cancel_request(request_id, user.email)
    except KeyError:
        return JSONResponse(
            {"success": False, "message": "Request not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    logger.info(
        "write-upgrade request id=%s cancelled by %s",
        request_id,
        portal_auth.mask_email(user.email),
    )
    return JSONResponse(
        {"success": True, "request": deleted},
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/tokens/my-request", methods=["OPTIONS"])
async def tokens_my_request_options(request: Request) -> Response:
    """Preflight for /api/tokens/my-request (Horizon portability)."""
    return handle_options(request)


def _resolve_own_token(store, user_email: str, key: str):
    """Find the caller's token by exact id (key_hash) or prefix (T-11-04).

    Returns the entry or ``None``. Another user's id yields ``None`` (404
    upstream, no existence detail leaked).
    """
    own = [
        e
        for e in store.list_entries(include_revoked_expired=True)
        if e.username == user_email
    ]
    for entry in own:
        if entry.key_hash == key or entry.key_prefix.startswith(key):
            return entry
    return None


@mcp.custom_route("/api/tokens/revoke", methods=["POST"])
async def tokens_revoke(request: Request) -> Response:
    """Revoke the caller's own token; it stops working immediately (D-14)."""
    user = portal_auth.require_user(request)
    if user is None:
        return _deny_401(request)
    body = await _read_json(request)
    key = body.get("id_or_prefix") or body.get("id") or body.get("prefix")
    if not key or not str(key).strip():
        return JSONResponse(
            {"success": False, "message": "Token id is required."},
            status_code=400,
            headers=_cors_headers(request),
        )
    key = str(key).strip()
    store = get_token_store()
    target = _resolve_own_token(store, user.email, key)
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
        "token %s...%s revoked by %s",
        entry.key_prefix,
        entry.key_suffix,
        portal_auth.mask_email(user.email),
    )
    return JSONResponse(
        {"success": True, "status": "revoked", "prefix": entry.key_prefix},
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/tokens/revoke", methods=["OPTIONS"])
async def tokens_revoke_options(request: Request) -> Response:
    """Preflight for /api/tokens/revoke (Horizon portability)."""
    return handle_options(request)


@mcp.custom_route("/api/tokens/rotate", methods=["POST"])
async def tokens_rotate(request: Request) -> Response:
    """Rotate the caller's own token: old revoked, new minted carrying
    identity/TTL with a one-time reveal (D-14, TOK-06 parity)."""
    user = portal_auth.require_user(request)
    if user is None:
        return _deny_401(request)
    body = await _read_json(request)
    key = body.get("id_or_prefix") or body.get("id") or body.get("prefix")
    if not key or not str(key).strip():
        return JSONResponse(
            {"success": False, "message": "Token id is required."},
            status_code=400,
            headers=_cors_headers(request),
        )
    key = str(key).strip()
    store = get_token_store()
    target = _resolve_own_token(store, user.email, key)
    if target is None:
        return JSONResponse(
            {"success": False, "message": "Token not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    override = body.get("expires_at")
    try:
        if override is None:
            new_raw, new_entry = store.rotate_by_prefix(target.key_prefix)
        else:
            new_raw, new_entry = store.rotate_by_prefix(
                target.key_prefix, expires_at=override
            )
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
        "token %s...%s rotated by %s to %s...%s",
        target.key_prefix,
        target.key_suffix,
        portal_auth.mask_email(user.email),
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


@mcp.custom_route("/api/tokens/rotate", methods=["OPTIONS"])
async def tokens_rotate_options(request: Request) -> Response:
    """Preflight for /api/tokens/rotate (Horizon portability)."""
    return handle_options(request)
