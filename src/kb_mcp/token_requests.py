"""Write-upgrade request store (Phase 11-01, D-01..D-04).

Tracks user requests for read-write tokens beside the ``tokens`` table.
One pending request max per user (D-03); denied rows stay visible with a
timestamp and re-request is allowed (D-04).

Import-safe: zero I/O and zero required env at import. All DB access happens
per-call via :mod:`kb_mcp.db` (``with connect() as conn, ...``). Logs carry
masked emails only (never raw addresses, never secrets).
"""

import logging

from kb_mcp.portal_auth import mask_email

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_DENIED = "denied"

_DECISIONS = (STATUS_APPROVED, STATUS_DENIED)

_COLUMNS = "id, user_email, status, created_at, decided_at, decided_by"


class RequestConflict(Exception):
    """A pending request already exists for this user (D-03 singleton)."""


def _row_to_dict(row) -> dict:
    """Convert a token_requests row to a JSON-serializable dict."""
    request_id, user_email, status, created_at, decided_at, decided_by = row

    def _iso(value):
        if value is None:
            return None
        if isinstance(value, str):
            return value
        try:
            return value.isoformat()
        except Exception:
            return str(value)

    return {
        "id": request_id,
        "user_email": user_email,
        "status": status,
        "created_at": _iso(created_at),
        "decided_at": _iso(decided_at),
        "decided_by": decided_by,
    }


def create_request(user_email: str) -> dict:
    """Create a pending request for ``user_email``.

    Raises :class:`RequestConflict` when a pending row already exists for
    that email (D-03). Raises ``ValueError`` on blank email.
    """
    from kb_mcp.db import connect

    email = (user_email or "").strip()
    if not email:
        raise ValueError("user_email must be non-empty")
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM token_requests "
            "WHERE user_email = %s AND status = 'pending' LIMIT 1",
            (email,),
        )
        if cur.fetchone() is not None:
            logger.info(
                "duplicate write-upgrade request rejected for %s",
                mask_email(email),
            )
            raise RequestConflict(
                "A pending request already exists for this user."
            )
        cur.execute(
            "INSERT INTO token_requests (user_email, status) "
            "VALUES (%s, 'pending') "
            f"RETURNING {_COLUMNS}",
            (email,),
        )
        row = cur.fetchone()
    logger.info("write-upgrade request created for %s", mask_email(email))
    return _row_to_dict(row)


def get_user_requests(user_email: str) -> list[dict]:
    """All requests for ``user_email``, oldest first (``ORDER BY created_at ASC``)."""
    from kb_mcp.db import connect

    email = (user_email or "").strip()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLUMNS} FROM token_requests "  # noqa: S608 - fixed columns
            "WHERE user_email = %s ORDER BY created_at ASC",
            (email,),
        )
        return [_row_to_dict(row) for row in cur.fetchall()]


def cancel_request(request_id, user_email: str) -> dict:
    """Delete the caller's own pending request (D-03).

    Only a row matching ``(id, user_email, status='pending')`` is removed;
    anything else raises ``KeyError`` (message-only 404 upstream, no
    existence detail leaked across users).
    """
    from kb_mcp.db import connect

    email = (user_email or "").strip()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLUMNS} FROM token_requests "  # noqa: S608 - fixed columns
            "WHERE id = %s AND user_email = %s AND status = 'pending'",
            (request_id, email),
        )
        row = cur.fetchone()
        if row is None:
            logger.info(
                "cancel rejected for request id=%s by %s",
                request_id,
                mask_email(email),
            )
            raise KeyError(f"No pending request found for id '{request_id}'.")
        cur.execute(
            "DELETE FROM token_requests WHERE id = %s",
            (request_id,),
        )
    logger.info(
        "write-upgrade request id=%s cancelled by %s",
        request_id,
        mask_email(email),
    )
    return _row_to_dict(row)


def set_decision(request_id, status: str, decided_by: str | None) -> dict:
    """Approve or deny a request, stamping ``decided_at=now()`` (D-04/D-09).

    ``status`` must be ``'approved'`` or ``'denied'`` (``ValueError``
    otherwise). Unknown ids raise ``KeyError``.
    """
    from kb_mcp.db import connect

    if status not in _DECISIONS:
        raise ValueError(
            f"status must be one of {list(_DECISIONS)}, got {status!r}."
        )
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE token_requests "
            "SET status = %s, decided_at = now(), decided_by = %s "
            "WHERE id = %s "
            f"RETURNING {_COLUMNS}",
            (status, decided_by, request_id),
        )
        row = cur.fetchone()
        if row is None:
            raise KeyError(f"No request found for id '{request_id}'.")
    logger.info(
        "request id=%s decided %s by %s",
        request_id,
        status,
        mask_email(decided_by),
    )
    return _row_to_dict(row)


def get_pending() -> list[dict]:
    """All pending requests, oldest first (queue order per D-09)."""
    from kb_mcp.db import connect

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLUMNS} FROM token_requests "  # noqa: S608 - fixed columns
            "WHERE status = 'pending' ORDER BY created_at ASC"
        )
        return [_row_to_dict(row) for row in cur.fetchall()]


def get_decided(limit: int = 50) -> list[dict]:
    """Decided (approved/denied) requests, newest decision first (D-09 history).

    Additive helper for the Plan 02 admin queue — existing functions untouched.
    """
    from kb_mcp.db import connect

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLUMNS} FROM token_requests "  # noqa: S608 - fixed columns
            "WHERE status IN ('approved', 'denied') "
            "ORDER BY decided_at DESC NULLS LAST, id DESC "
            "LIMIT %s",
            (limit,),
        )
        return [_row_to_dict(row) for row in cur.fetchall()]


__all__ = [
    "STATUS_APPROVED",
    "STATUS_DENIED",
    "STATUS_PENDING",
    "RequestConflict",
    "cancel_request",
    "create_request",
    "get_decided",
    "get_pending",
    "get_user_requests",
    "set_decision",
]
