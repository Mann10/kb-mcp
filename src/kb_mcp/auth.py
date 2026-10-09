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
        )
        self._entries[entry.key_hash] = entry
        self.save()
        return raw, entry

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
