"""Typed, hashed token model and persistence for AUTH-01.

Transport-agnostic auth core: no SDK imports, no stdout writes.
Raw tokens exist only at generation time (returned once from
:meth:`TokenStore.add_token`); only SHA-256 hex digests rest on disk.
"""

import hashlib
import logging
import os
import secrets
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, TypeAdapter, field_validator

logger = logging.getLogger(__name__)


class TokenType(str, Enum):
    """Token permission tier. Scopes derive from the type (single source)."""

    READ = "read"
    READ_WRITE = "read_write"

    @property
    def scopes(self) -> list[str]:
        """Scope strings granted to this tier (stable cross-phase contract)."""
        if self is TokenType.READ_WRITE:
            return ["notes:read", "notes:write"]
        return ["notes:read"]


class TokenEntry(BaseModel):
    """A single issued token. ``key_hash`` is SHA-256 hex, never the secret."""

    key_hash: str = Field(repr=False)
    key_prefix: str
    key_suffix: str
    username: str
    token_type: TokenType
    created_at: str
    last_used_at: str | None = None
    revoked_at: str | None = None
    expires_at: str | None = None

    @field_validator("username")
    @classmethod
    def username_must_be_non_empty(cls, v: str) -> str:
        """Validate username is non-empty after stripping whitespace."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("username must be non-empty")
        return stripped

    @property
    def scopes(self) -> list[str]:
        """Scopes derived from the entry's type (never stored independently)."""
        return self.token_type.scopes


_entry_list_adapter = TypeAdapter(list[TokenEntry])


def _hash_token(raw: str) -> str:
    """SHA-256 hex digest of a raw token (one-way; leaks yield nothing)."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_token() -> str:
    """Generate a 256-bit URL-safe bearer token with OS entropy."""
    return secrets.token_urlsafe(32)


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _parse_expiry(value: str | None) -> datetime | None:
    """Parse an ISO-8601 expiry string; naive values are assumed UTC."""
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def token_status(entry: TokenEntry) -> str:
    """Classify an entry for CLI rendering: revoked, expired, or active."""
    if entry.revoked_at is not None:
        return "revoked"
    if entry.expires_at is None:
        return "active"
    try:
        expiry = _parse_expiry(entry.expires_at)
    except ValueError:
        logger.warning(
            "Token %s...%s has unparsable expires_at; treating as expired",
            entry.key_prefix,
            entry.key_suffix,
        )
        return "expired"
    if expiry is not None and expiry <= datetime.now(timezone.utc):
        return "expired"
    return "active"


class TokenStore:
    """JSON-backed token registry keyed by hash, hashes only on disk."""

    def __init__(self, store_path: Path | None = None):
        if store_path is None:
            env_path = os.environ.get("KB_TOKENS_FILE")
            if env_path:
                store_path = Path(env_path)
            else:
                store_path = Path.home() / "knowledge-base" / ".tokens.json"
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: dict[str, TokenEntry] = {}

    def __len__(self) -> int:
        return len(self._entries)

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
        self._entries[entry.key_hash] = entry
        self.save()
        return raw, entry

    def find_by_prefix(self, prefix: str) -> list[TokenEntry]:
        """Find entries whose display prefix starts with the given prefix."""
        if not prefix or not prefix.strip():
            return []
        matches = [e for e in self._entries.values() if e.key_prefix.startswith(prefix)]
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
        self.save()
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
        new_raw, new_entry = self.add_token(
            username=old.username,
            token_type=old.token_type,
            expires_at=(expires_at if expires_at is not None else old.expires_at),
        )
        logger.info(
            "Rotated token %s...%s (user=%s) to %s...%s",
            old.key_prefix,
            old.key_suffix,
            old.username,
            new_entry.key_prefix,
            new_entry.key_suffix,
        )
        self.save()
        return (new_raw, new_entry)

    def list_entries(
        self, include_revoked_expired: bool = False
    ) -> list[TokenEntry]:
        """List entries sorted by (created_at, username), optionally filtered."""
        entries = list(self._entries.values())
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
        entry = self._entries.get(candidate_hash)
        if entry is None:
            return None
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
        if expiry is not None and expiry <= datetime.now(timezone.utc):
            return None
        return entry

    def save(self) -> None:
        """Atomically persist entries (temp-file + rename); hashes only."""
        content = _entry_list_adapter.dump_json(list(self._entries.values()), indent=2).decode(
            "utf-8"
        )
        temp_path = self.store_path.with_suffix(".tmp")
        try:
            temp_path.write_text(content, encoding="utf-8")
            os.replace(temp_path, self.store_path)
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    @classmethod
    def load(cls, store_path: Path | None = None) -> "TokenStore":
        """Load a store from disk; missing/corrupt files yield an empty store."""
        store = cls(store_path=store_path)
        try:
            text = store.store_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning("Token store %s missing; starting empty", store.store_path)
            return store
        except Exception as e:
            logger.warning("Token store %s unreadable (%s); starting empty", store.store_path, e)
            return store
        try:
            entries = _entry_list_adapter.validate_json(text)
        except Exception as e:
            logger.warning("Token store %s corrupt (%s); starting empty", store.store_path, e)
            return store
        store._entries = {entry.key_hash: entry for entry in entries}
        return store

    def update_last_used(self, raw: str | None) -> None:
        """Stamp last_used_at. Telemetry fail-open: persistence failure only warns."""
        if raw is None or not raw.strip():
            return
        entry = self._entries.get(_hash_token(raw))
        if entry is None:
            return
        entry.last_used_at = utc_now_iso()
        try:
            self.save()
        except Exception as e:
            logger.warning(
                "Token usage telemetry for %s...%s not persisted (%s)",
                entry.key_prefix,
                entry.key_suffix,
                e,
            )
