"""Append-only audit log over Supabase Postgres (V2-02).

Mirrors the file audit contract: one row per write carrying user, tool, file,
timestamp. Writes are fail-open — a database error warns and returns so audit
never blocks a note write, consistent with the fail-open file precedent.

Raw token secrets never flow through this module (callers pass usernames only).
"""

import logging

from .db import connect

logger = logging.getLogger("kb_mcp.audit")


def audit_write_db(username: str, tool: str, filename: str) -> None:
    """Append one audit row (user, tool, file, timestamp), fail-open."""
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO audit_log (username, tool, filename) VALUES (%s, %s, %s)",
                (username, tool, filename),
            )
    except Exception as e:
        logger.warning("audit append failed: %s", e)
        return


__all__ = ["audit_write_db"]
