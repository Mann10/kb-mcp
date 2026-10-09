"""Shared pytest fixtures for all test modules."""

import pytest

from kb_mcp.storage import NoteRepository


@pytest.fixture
def notes_dir(tmp_path):
    """Create a temporary directory for notes."""
    d = tmp_path / "notes"
    d.mkdir()
    return d


@pytest.fixture
def repository(notes_dir):
    """Create a NoteRepository instance with temp notes_dir."""
    return NoteRepository(notes_dir=notes_dir)


@pytest.fixture
def valid_frontmatter():
    """Return a dict with valid frontmatter data."""
    return {
        "title": "Test Note",
        "tags": ["test", "integration"],
        "created": "2026-10-09",
    }


@pytest.fixture
def sample_note_content():
    """Return a string with valid markdown content including frontmatter delimiters."""
    return (
        "---\n"
        'title: "Sample Note"\n'
        "tags: [test, sample]\n"
        'created: "2026-10-09"\n'
        "---\n"
        "\n"
        "# Sample Note\n"
        "\n"
        "This is sample note content for testing.\n"
    )


@pytest.fixture
def token_store_path(tmp_path):
    """Isolated token-store file path for a single test (never shared)."""
    return tmp_path / ".tokens.json"


@pytest.fixture
def token_store(token_store_path):
    """TokenStore backed by an isolated tmp_path file.

    Imports are function-local so this module stays importable before
    src/kb_mcp/auth.py exists (Wave 0 RED affects test_auth.py only).
    """
    from kb_mcp.auth import TokenStore

    return TokenStore(store_path=token_store_path)


@pytest.fixture
def read_token_pair(token_store):
    """(raw, entry) for a READ token for user "test-reader"."""
    from kb_mcp.auth import TokenType

    raw = "test-token-aaa-reader-0001"
    _, entry = token_store.add_token(
        username="test-reader", token_type=TokenType.READ, raw=raw
    )
    return (raw, entry)


@pytest.fixture
def read_write_token_pair(token_store):
    """(raw, entry) for a READ_WRITE token for user "test-writer"."""
    from kb_mcp.auth import TokenType

    raw = "test-token-aaa-writer-0002"
    _, entry = token_store.add_token(
        username="test-writer", token_type=TokenType.READ_WRITE, raw=raw
    )
    return (raw, entry)


@pytest.fixture
def shared_prefix_store(token_store_path):
    """TokenStore with two entries sharing a 4-char prefix but distinct 8-char prefixes."""
    from kb_mcp.auth import TokenStore, TokenType

    store = TokenStore(store_path=token_store_path)
    store.add_token(
        username="shared-alice", token_type=TokenType.READ, raw="test-aaaa-shared-0001"
    )
    store.add_token(
        username="shared-bob", token_type=TokenType.READ, raw="test-bbbb-shared-0002"
    )
    return store


@pytest.fixture
def revoked_entry_store(token_store_path):
    """TokenStore with a single entry revoked via the real revoke path."""
    from kb_mcp.auth import TokenStore, TokenType

    store = TokenStore(store_path=token_store_path)
    _, entry = store.add_token(
        username="revoked-user",
        token_type=TokenType.READ,
        raw="test-token-aaa-revoked-0010",
    )
    store.revoke_by_prefix(entry.key_prefix[:4])
    return store


@pytest.fixture
def expired_entry_store(token_store_path):
    """TokenStore with a single entry carrying a past expires_at."""
    from kb_mcp.auth import TokenStore, TokenType

    store = TokenStore(store_path=token_store_path)
    store.add_token(
        username="expired-user",
        token_type=TokenType.READ,
        raw="test-token-aaa-expired-0011",
        expires_at="2000-01-01T00:00:00+00:00",
    )
    return store
