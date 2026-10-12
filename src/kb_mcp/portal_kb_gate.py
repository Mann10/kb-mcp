"""KB browse/edit write-access gate (Phase 12-01 task 1).

Single choke point for the D-13 rule: a portal user is write-authorized
iff they own at least one active read-write token. Imported by both the
read routes (``can_write``) and the write routes (per-route 403 gate).

Import-safe: zero I/O and zero required env at import. The token store is
resolved per call via :mod:`kb_mcp.backend` so tests can monkeypatch it.
Fail-closed on every path: empty/non-string email, store errors, revoked,
expired, or read-only entries all yield ``False``.
"""

from kb_mcp.auth import TokenType, token_status


def _is_read_write(token_type) -> bool:
    """True when the entry type grants write scope (dash/underscore tolerant)."""
    try:
        if token_type == TokenType.READ_WRITE:
            return True
    except Exception:
        pass
    try:
        value = token_type.value if hasattr(token_type, "value") else token_type
    except Exception:
        return False
    try:
        norm = str(value).strip().lower().replace("-", "_")
    except Exception:
        return False
    return norm == TokenType.READ_WRITE.value


def has_write_access(email: str) -> bool:
    """Return True iff ``email`` owns an active read-write token.

    Fail-closed: empty/non-string email → False; any store exception →
    False; revoked/expired/read-only entries never grant access.
    """
    if not isinstance(email, str) or not email.strip():
        return False
    try:
        from kb_mcp.backend import get_token_store

        store = get_token_store()
        entries = store.list_entries(include_revoked_expired=True)
    except Exception:
        return False
    try:
        for entry in entries or []:
            try:
                if getattr(entry, "username", None) != email:
                    continue
                if not _is_read_write(getattr(entry, "token_type", None)):
                    continue
                if token_status(entry) != "active":
                    continue
            except Exception:
                continue
            return True
    except Exception:
        return False
    return False
