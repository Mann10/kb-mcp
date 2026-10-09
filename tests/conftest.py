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
