"""Supabase-backed token store (V2-02).

Same API and semantics as :class:`TokenStore` (filesystem): hash-only storage,
prefix display strings, soft-revoke with cardinality gate, TTL carried verbatim
as ISO-8601 text, fail-closed lookup, fail-open usage telemetry. The v1 model
(:class:`TokenEntry`) and helpers are reused directly — only persistence moves.

Connections are per-operation via :mod:`kb_mcp.db` (no pooling by design).
"""

import logging
import secrets

from .auth import (
    TokenEntry,
    TokenType,
    _hash_token,
    _parse_expiry,
    generate_token,
    token_status,
    utc_now_iso,
)
from .db import connect

logger = logging.getLogger(__name__)

_COLUMNS = (
    "key_hash, key_prefix, key_suffix, username, token_type,"
    " created_at, last_used_at, revoked_at, expires_at"
)


def _row_to_entry(row) -> TokenEntry:
    """Build a TokenEntry from a tokens row (same field order as _COLUMNS)."""
    (
        key_hash,
        key_prefix,
        key_suffix,
        username,
        token_type,
        created_at,
        last_used_at,
        revoked_at,
        expires_at,
    ) = row
    return TokenEntry(
        key_hash=key_hash,
        key_prefix=key_prefix,
        key_suffix=key_suffix,
        username=username,
        token_type=TokenType(token_type),
        created_at=created_at,
        last_used_at=last_used_at,
        revoked_at=revoked_at,
        expires_at=expires_at,
    )


class SupabaseTokenStore:
    """Token registry over Supabase Postgres; hashes only, never secrets."""

    @classmethod
    def load(cls) -> "SupabaseTokenStore":
        """Return a store bound to SUPABASE_DB_URL (mirrors TokenStore.load)."""
        return cls()

    def __len__(self) -> int:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM tokens")
            return cur.fetchone()[0]

    def add_token(
        self,
        username: str,
        token_type: TokenType,
        raw: str | None = None,
        expires_at: str | None = None,
    ) -> tuple[str, TokenEntry]:
        """Issue a token; the raw secret is returned once and never stored."""
        if raw is None:
            raw = generate_token()
        entry = TokenEntry(
            key_hash=_hash_token(raw),
            key_prefix=raw[:8],
            key_suffix=raw[-4:],
            username=username,
            token_type=token_type,
            created_at=utc_now_iso(),
            expires_at=expires_at,
        )
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tokens "
                "(key_hash, key_prefix, key_suffix, username, token_type,"
                " created_at, last_used_at, revoked_at, expires_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    entry.key_hash,
                    entry.key_prefix,
                    entry.key_suffix,
                    entry.username,
                    entry.token_type.value,
                    entry.created_at,
                    entry.last_used_at,
                    entry.revoked_at,
                    entry.expires_at,
                ),
            )
        return raw, entry

    def _all_entries(self) -> list[TokenEntry]:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {_COLUMNS} FROM tokens")  # noqa: S608 - fixed columns
            return [_row_to_entry(row) for row in cur.fetchall()]

    def find_by_prefix(self, prefix: str) -> list[TokenEntry]:
        """Find entries whose display prefix starts with the given prefix."""
        if not prefix or not prefix.strip():
            return []
        matches = [e for e in self._all_entries() if e.key_prefix.startswith(prefix)]
        return sorted(matches, key=lambda e: (e.username, e.created_at))

    def revoke_by_prefix(self, prefix: str) -> TokenEntry:
        """Soft-revoke the single entry matching prefix; fail on 0 or 2+ matches."""
        matches = self.find_by_prefix(prefix)
        if len(matches) == 0:
            raise KeyError(f"No token found for prefix '{prefix}'.")
        if len(matches) >= 2:
            candidates = "; ".join(
                f"{e.key_prefix}...{e.key_suffix} ({e.username})" for e in matches
            )
            raise KeyError(
                f"Ambiguous prefix '{prefix}' matches {len(matches)} tokens. "
                f"Use a longer prefix. {candidates}"
            )
        entry = matches[0]
        entry.revoked_at = utc_now_iso()
        logger.info(
            "Revoked token %s...%s (user=%s)",
            entry.key_prefix,
            entry.key_suffix,
            entry.username,
        )
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE tokens SET revoked_at = %s WHERE key_hash = %s",
                (entry.revoked_at, entry.key_hash),
            )
        return entry

    def rotate_by_prefix(
        self, prefix: str, expires_at: str | None = None
    ) -> tuple[str, TokenEntry]:
        """Atomically revoke the matched entry and mint its replacement."""
        matches = self.find_by_prefix(prefix)
        if len(matches) == 0:
            raise KeyError(f"No token found for prefix '{prefix}'.")
        if len(matches) >= 2:
            candidates = "; ".join(
                f"{e.key_prefix}...{e.key_suffix} ({e.username})" for e in matches
            )
            raise KeyError(
                f"Ambiguous prefix '{prefix}' matches {len(matches)} tokens. "
                f"Use a longer prefix. {candidates}"
            )
        old = matches[0]
        old.revoked_at = utc_now_iso()
        new_raw = generate_token()
        new_entry = TokenEntry(
            key_hash=_hash_token(new_raw),
            key_prefix=new_raw[:8],
            key_suffix=new_raw[-4:],
            username=old.username,
            token_type=old.token_type,
            created_at=utc_now_iso(),
            expires_at=(expires_at if expires_at is not None else old.expires_at),
        )
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE tokens SET revoked_at = %s WHERE key_hash = %s",
                (old.revoked_at, old.key_hash),
            )
            cur.execute(
                "INSERT INTO tokens "
                "(key_hash, key_prefix, key_suffix, username, token_type,"
                " created_at, last_used_at, revoked_at, expires_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    new_entry.key_hash,
                    new_entry.key_prefix,
                    new_entry.key_suffix,
                    new_entry.username,
                    new_entry.token_type.value,
                    new_entry.created_at,
                    new_entry.last_used_at,
                    new_entry.revoked_at,
                    new_entry.expires_at,
                ),
            )
        logger.info(
            "Rotated token %s...%s (user=%s) to %s...%s",
            old.key_prefix,
            old.key_suffix,
            old.username,
            new_entry.key_prefix,
            new_entry.key_suffix,
        )
        return (new_raw, new_entry)

    def list_entries(
        self, include_revoked_expired: bool = False
    ) -> list[TokenEntry]:
        """List entries sorted by (created_at, username), optionally filtered."""
        from datetime import datetime, timezone

        entries = self._all_entries()
        if include_revoked_expired:
            return sorted(entries, key=lambda e: (e.created_at, e.username))
        now = datetime.now(timezone.utc)
        active: list[TokenEntry] = []
        for entry in entries:
            if entry.revoked_at is not None:
                continue
            if entry.expires_at is not None:
                try:
                    expiry = _parse_expiry(entry.expires_at)
                except ValueError:
                    continue
                if expiry is not None and expiry <= now:
                    continue
            active.append(entry)
        return sorted(active, key=lambda e: (e.created_at, e.username))

    def lookup(self, raw: str | None) -> TokenEntry | None:
        """Return the entry for a raw token, or None on ANY failure (fail-closed)."""
        if raw is None or not raw.strip():
            return None
        candidate_hash = _hash_token(raw)
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT {_COLUMNS} FROM tokens WHERE key_hash = %s",  # noqa: S608
                (candidate_hash,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        entry = _row_to_entry(row)
        if not secrets.compare_digest(entry.key_hash, candidate_hash):
            return None
        if entry.revoked_at is not None:
            return None
        try:
            expiry = _parse_expiry(entry.expires_at)
        except ValueError:
            logger.warning(
                "Denying token %s...%s: unparsable expires_at",
                entry.key_prefix,
                entry.key_suffix,
            )
            return None
        from datetime import datetime, timezone

        if expiry is not None and expiry <= datetime.now(timezone.utc):
            return None
        return entry

    def update_last_used(self, raw: str | None) -> None:
        """Stamp last_used_at. Telemetry fail-open: failure only warns."""
        if raw is None or not raw.strip():
            return
        try:
            with connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE tokens SET last_used_at = %s WHERE key_hash = %s",
                    (utc_now_iso(), _hash_token(raw)),
                )
        except Exception as e:
            logger.warning("Token usage telemetry not persisted (%s)", e)


__all__ = ["SupabaseTokenStore", "token_status"]
