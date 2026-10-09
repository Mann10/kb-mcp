"""Model + store proofs for the typed, hashed token foundation (AUTH-01).

Failing-first scaffold (Wave 0): every test here requires src/kb_mcp/auth.py
(TokenType, TokenEntry, TokenStore). All token values are obviously-fake
("test-token-...") per research Pitfall P-3 — never real secrets.
"""

import logging

import pytest

from kb_mcp.auth import TokenEntry, TokenStore, TokenType


def test_read_scopes():
    """TokenType.READ derives exactly ["notes:read"]."""
    assert TokenType.READ.scopes == ["notes:read"]


def test_read_write_scopes():
    """TokenType.READ_WRITE derives ["notes:read", "notes:write"]."""
    assert TokenType.READ_WRITE.scopes == ["notes:read", "notes:write"]


def test_entry_scopes_delegate_to_type(read_token_pair, read_write_token_pair):
    """TokenEntry.scopes is derived from its type, never stored independently."""
    _, read_entry = read_token_pair
    _, rw_entry = read_write_token_pair
    assert read_entry.scopes == ["notes:read"]
    assert rw_entry.scopes == ["notes:read", "notes:write"]


def test_store_roundtrip(token_store_path):
    """Add entry, save, fresh-load: entry present with same hash/user/type."""
    store = TokenStore(store_path=token_store_path)
    raw, entry = store.add_token(
        username="roundtrip-user",
        token_type=TokenType.READ_WRITE,
        raw="test-token-aaa-roundtrip-0001",
    )
    store.save()

    fresh = TokenStore.load(store_path=token_store_path)
    found = fresh.lookup(raw)
    assert found is not None
    assert found.key_hash == entry.key_hash
    assert found.username == "roundtrip-user"
    assert found.token_type == TokenType.READ_WRITE


def test_no_plaintext_on_disk(token_store_path):
    """V-5: store file contains key_hash but never the raw token."""
    store = TokenStore(store_path=token_store_path)
    raw, _ = store.add_token(
        username="plaintext-user",
        token_type=TokenType.READ,
        raw="test-token-aaa-no-plaintext-0002",
    )
    store.save()

    text = token_store_path.read_text(encoding="utf-8")
    assert raw not in text
    assert "key_hash" in text


def test_missing_store(token_store_path, caplog):
    """V-6: missing store file loads empty (no raise)."""
    assert not token_store_path.exists()
    with caplog.at_level(logging.WARNING):
        store = TokenStore.load(store_path=token_store_path)
    assert len(store) == 0
    assert store.lookup("test-token-aaa-missing-0003") is None


def test_corrupt_store(token_store_path, caplog):
    """V-6: corrupt JSON loads empty with warning (no raise, denies cleanly)."""
    token_store_path.write_text("{not valid json [[[", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        store = TokenStore.load(store_path=token_store_path)
    assert len(store) == 0
    assert store.lookup("test-token-aaa-corrupt-0004") is None


def test_unknown_token_verifies_none(token_store):
    """Lookup of a never-issued token returns None."""
    assert token_store.lookup("test-token-aaa-unknown-0005") is None
    assert token_store.lookup(None) is None
    assert token_store.lookup("") is None
    assert token_store.lookup("   ") is None


def test_revoked_token_verifies_none(token_store):
    """An entry with revoked_at set verifies to None."""
    from kb_mcp.auth import utc_now_iso

    raw, entry = token_store.add_token(
        username="revoked-user",
        token_type=TokenType.READ_WRITE,
        raw="test-token-aaa-revoked-0006",
    )
    assert token_store.lookup(raw) is not None
    entry.revoked_at = utc_now_iso()
    token_store.save()
    assert token_store.lookup(raw) is None


def test_repr_excludes_secrets(read_token_pair):
    """repr(entry) contains neither the raw token nor the full key_hash."""
    raw, entry = read_token_pair
    assert isinstance(entry, TokenEntry)
    text = repr(entry)
    assert raw not in text
    assert entry.key_hash not in text


def test_authentication_error_defaults():
    """AuthenticationError carries its default message via str()."""
    from kb_mcp.errors import AuthenticationError

    assert str(AuthenticationError()) == "Invalid or missing token."
    assert str(AuthenticationError("custom reason")) == "custom reason"


def test_authorization_error_message():
    """AuthorizationError str returns the constructor message."""
    from kb_mcp.errors import AuthorizationError

    assert str(AuthorizationError("Write access required.")) == "Write access required."


def test_expired_token_verifies_none(token_store):
    """An entry with a past expires_at verifies to None; future expiry passes."""
    raw_past, _ = token_store.add_token(
        username="expired-user",
        token_type=TokenType.READ,
        raw="test-token-aaa-expired-0007",
    )
    raw_future, _ = token_store.add_token(
        username="fresh-user",
        token_type=TokenType.READ,
        raw="test-token-aaa-future-0008",
    )
    # Backdate one entry to a past expiry; set the other far in the future.
    for entry in token_store._entries.values():
        if entry.username == "expired-user":
            entry.expires_at = "2000-01-01T00:00:00+00:00"
        elif entry.username == "fresh-user":
            entry.expires_at = "2099-01-01T00:00:00+00:00"
    token_store.save()
    assert token_store.lookup(raw_past) is None
    assert token_store.lookup(raw_future) is not None


def test_add_token_generates_unique_values(token_store):
    """add_token without raw generates distinct, non-empty secrets."""
    raw1, entry1 = token_store.add_token(username="gen-a", token_type=TokenType.READ)
    raw2, entry2 = token_store.add_token(username="gen-b", token_type=TokenType.READ)
    assert raw1 and raw2 and raw1 != raw2
    assert entry1.key_hash != entry2.key_hash
    assert entry1.key_prefix == raw1[:8]
    assert entry1.key_suffix == raw1[-4:]


def test_update_last_used_never_blocks(token_store):
    """update_last_used persists telemetry but never raises on failure."""
    raw, _ = token_store.add_token(
        username="telemetry-user",
        token_type=TokenType.READ,
        raw="test-token-aaa-telemetry-0009",
    )
    token_store.update_last_used(raw)
    assert token_store.lookup(raw) is not None
    assert token_store.lookup(raw).last_used_at is not None
    # Unknown token telemetry is a silent no-op, not an error.
    token_store.update_last_used("test-token-aaa-telemetry-unknown")
