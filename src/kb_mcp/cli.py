"""Typer operator CLI for knowledge-base MCP token management."""

import re
from datetime import datetime, timedelta, timezone
from typing import Annotated

import typer

from kb_mcp.auth import TokenStore, TokenType, token_status

app = typer.Typer(help="Manage knowledge-base MCP tokens.")


def _get_store() -> TokenStore:
    """Load the token store (KB_TOKENS_FILE honored inside TokenStore.load)."""
    return TokenStore.load()


def _normalize_type(v: str) -> TokenType:
    """Normalize a --type flag value to a TokenType (fail-closed default read)."""
    lowered = v.strip().lower()
    if lowered == "read":
        return TokenType.READ
    if lowered in ("read-write", "read_write"):
        return TokenType.READ_WRITE
    raise typer.BadParameter(f"Invalid --type '{v}': choose read or read-write")


_TTL_RE = re.compile(r"^(?P<n>\d+)(?P<u>[smhd])?$")
_MULT = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_ttl_duration(value: str) -> timedelta:
    """Parse a TTL string like 30d, 24h, 15m, 3600 into a timedelta."""
    m = _TTL_RE.match(value.strip())
    if not m:
        raise typer.BadParameter(
            f"Invalid TTL '{value}': use <number>[s|m|h|d], e.g. 30d, 24h, 15m, 3600"
        )
    amount = int(m.group("n"))
    unit = m.group("u") or "s"
    return timedelta(seconds=amount * _MULT[unit])


def _expires_at_from_ttl(ttl: str | None) -> str | None:
    """Convert a TTL flag value to a UTC ISO-8601 expiry, or None when omitted."""
    if ttl is None:
        return None
    return (datetime.now(timezone.utc) + parse_ttl_duration(ttl)).isoformat()


def _display(entry) -> str:
    """Truncated display string for an entry (prefix...suffix, never the secret)."""
    return f"{entry.key_prefix}...{entry.key_suffix}"


def _status(entry) -> str:
    """Classify an entry for rendering (revoked > expired > active)."""
    return token_status(entry)


@app.command()
def generate(
    username: Annotated[str, typer.Argument(help="Owner of the new token")],
    type: Annotated[str, typer.Option("--type", help="Token permission: read or read-write")] = "read",
    ttl: Annotated[str | None, typer.Option(help="Time-to-live like 30d, 24h, 15m, 3600")] = None,
) -> None:
    """Generate a new token for USERNAME (default read-only, printed once)."""
    token_type = _normalize_type(type)
    if not username.strip():
        raise typer.BadParameter("username must be non-empty")
    store = _get_store()
    raw, entry = store.add_token(
        username=username.strip(),
        token_type=token_type,
        expires_at=_expires_at_from_ttl(ttl),
    )
    typer.echo(f"Token for '{entry.username}': {raw}")
    typer.echo("Store this token securely. It will not be shown again.")
