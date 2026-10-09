"""SC-1..SC-4 middleware proofs (AUTH-01 end-to-end, AUTH-02 enforcement).

Every test exercises the real decorator signature (``token`` / ``_store``
kwargs). The dummy tools below contain zero auth code by construction —
a grep gate in the plan enforces that their bodies never reference
verification helpers.
"""

import pytest

from kb_mcp.errors import AuthenticationError, AuthorizationError
from kb_mcp.middleware import (
    configure_default_store,
    require_read,
    require_write,
)

calls: list[str] = []


@require_read
def dummy_read(*, token=None, _store=None):
    return "read-ok"


@require_write
def dummy_write(*, token=None, _store=None):
    calls.append("write")
    return "write-ok"


@pytest.fixture(autouse=True)
def _clear_calls():
    calls.clear()
    yield
    calls.clear()


def test_read_token_allows_read(token_store, read_token_pair):
    raw, _ = read_token_pair
    assert dummy_read(token=raw, _store=token_store) == "read-ok"


def test_read_token_denied_write(token_store, read_token_pair):
    raw, _ = read_token_pair
    with pytest.raises(
        AuthorizationError,
        match="Write access required. Use a write token or contact the owner.",
    ):
        dummy_write(token=raw, _store=token_store)
    assert calls == []


def test_read_write_token_allows_both(token_store, read_write_token_pair):
    raw, _ = read_write_token_pair
    assert dummy_read(token=raw, _store=token_store) == "read-ok"
    assert dummy_write(token=raw, _store=token_store) == "write-ok"
    assert calls == ["write"]


def test_invalid_token_rejected_everywhere(token_store, read_write_token_pair):
    with pytest.raises(AuthenticationError, match="Invalid or missing token."):
        dummy_read(token="bogus-token-xyz", _store=token_store)
    with pytest.raises(AuthenticationError, match="Invalid or missing token."):
        dummy_write(token="bogus-token-xyz", _store=token_store)
    assert calls == []


def test_missing_token_rejected(token_store, read_write_token_pair):
    with pytest.raises(AuthenticationError, match="Invalid or missing token."):
        dummy_read(token=None, _store=token_store)
    with pytest.raises(AuthenticationError, match="Invalid or missing token."):
        dummy_write(token=None, _store=token_store)
    with pytest.raises(AuthenticationError, match="Invalid or missing token."):
        dummy_read(_store=token_store)
    with pytest.raises(AuthenticationError, match="Invalid or missing token."):
        dummy_write(_store=token_store)
    assert calls == []


def test_every_call_verified(token_store, read_write_token_pair):
    from kb_mcp.auth import utc_now_iso

    raw, entry = read_write_token_pair
    assert dummy_read(token=raw, _store=token_store) == "read-ok"
    entry.revoked_at = utc_now_iso()
    token_store.save()
    with pytest.raises(AuthenticationError, match="Invalid or missing token."):
        dummy_read(token=raw, _store=token_store)
    with pytest.raises(AuthenticationError, match="Invalid or missing token."):
        dummy_write(token=raw, _store=token_store)
    assert calls == []


def test_corrupt_store_denies(token_store_path):
    from kb_mcp.auth import TokenStore

    token_store_path.write_text("{ not valid json", encoding="utf-8")
    corrupt = TokenStore.load(token_store_path)
    with pytest.raises(AuthenticationError, match="Invalid or missing token."):
        dummy_read(token="bogus-token-xyz", _store=corrupt)
    with pytest.raises(AuthenticationError, match="Invalid or missing token."):
        dummy_write(token="bogus-token-xyz", _store=corrupt)
    assert calls == []


def test_unconfigured_store_denies(read_write_token_pair):
    configure_default_store(None)
    raw, _ = read_write_token_pair
    with pytest.raises(AuthenticationError, match="Invalid or missing token."):
        dummy_read(token=raw)
    with pytest.raises(AuthenticationError, match="Invalid or missing token."):
        dummy_write(token=raw)
    assert calls == []


def test_default_store_allows_read(token_store, read_token_pair):
    configure_default_store(token_store)
    try:
        raw, _ = read_token_pair
        assert dummy_read(token=raw) == "read-ok"
    finally:
        configure_default_store(None)
