"""Append-only audit log + structured logging helpers (D-15/D-16/D-18).

Transport-agnostic: no server imports, no TokenStore import (no coupling).
Raw token secrets never flow through this module — every log call routes
through :func:`mask_token`, which is the single secrecy choke point.

Policy (locked decisions):
- D-15: git history PLUS an append-only log line per write carrying
  user, tool, file, timestamp (exact order fixed in :func:`audit_write`).
- D-16: reads log light at INFO (tool name only, no payloads); writes +
  auth denials + rate-limit hits log with user/tool context.
- D-18: never log raw token secrets; at most prefix...suffix.

No rotation in this phase by design (single-process personal-KB scale;
operator controls the path via KB_AUDIT_FILE). Audit writes are fail-open:
an OSError warns and returns so audit never blocks a write, consistent
with the fail-open git precedent.
"""

import logging
import os
from pathlib import Path

from kb_mcp.auth import utc_now_iso

logger = logging.getLogger("kb_mcp.audit")


def mask_token(raw: str | None) -> str:
    """Mask a raw token for log output (central secrecy primitive).

    Returns "missing" for falsy input, "prefix...suffix" for len >= 8,
    else "****". Callers must pass raw secrets only here — never format
    a raw token directly into a log call.
    """
    if not raw:
        return "missing"
    if len(raw) >= 8:
        return f"{raw[:4]}...{raw[-4:]}"
    return "****"


def audit_log_path() -> Path:
    """Resolve the audit log path (operator-controlled via KB_AUDIT_FILE)."""
    env_path = os.environ.get("KB_AUDIT_FILE")
    if env_path:
        return Path(env_path)
    return Path.home() / "knowledge-base" / "mcp_audit.log"


def audit_write(
    username: str, tool: str, filename: str, log_path: Path | None = None
) -> None:
    """Append one D-15 field-set line (user, tool, file, timestamp), fail-open."""
    path = log_path if log_path is not None else audit_log_path()
    line = f"{utc_now_iso()} user={username} tool={tool} file={filename}\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError as e:
        logger.warning("audit append failed: %s", e)
        return


def log_read(tool: str) -> None:
    """Log a read at INFO with the tool name only (D-16 reads-light)."""
    logger.info("tool=%s", tool)


def log_write(
    username: str, tool: str, filename: str, log_path: Path | None = None
) -> None:
    """Log a write with user/tool context then append the audit line."""
    logger.info("user=%s tool=%s file=%s", username, tool, filename)
    audit_write(username, tool, filename, log_path=log_path)


def log_denial(kind: str, username: str | None, tool: str, masked: str) -> None:
    """Log an auth-denial or rate-limit hit with masked token context.

    Callers pass ``mask_token(raw)`` as ``masked`` — secrecy by construction.
    """
    logger.warning(
        "%s denied: user=%s tool=%s token=%s", kind, username or "unknown", tool, masked
    )
