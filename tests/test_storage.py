"""Tests for NoteRepository CRUD operations and atomic writes."""

from pathlib import Path

import pytest

from kb_mcp.errors import (
    InvalidTypeError,
    MalformedYAMLError,
    NoteNotFoundError,
    PathTraversalError,
)
from kb_mcp.storage import NoteRepository


class TestWriteNote:
    """Tests for NoteRepository.write_note."""

    def test_write_and_read_back_metadata_intact(self, tmp_path):
        """Test 1: Write a note with valid frontmatter, read it back — all metadata intact."""
        repo = NoteRepository(notes_dir=tmp_path)
        note = repo.write_note(
            filename="my-note.md",
            title="My Note",
            body="This is the body content.",
            tags=["work", "project-x"],
            created="2026-10-09",
        )
        assert note.filename == "my-note"
        assert note.metadata.title == "My Note"
        assert note.metadata.tags == ["work", "project-x"]
        assert note.metadata.created == "2026-10-09"
        assert note.body == "This is the body content."

        # Read it back
        read_note = repo.read_note("my-note.md")
        assert read_note.filename == "my-note"
        assert read_note.metadata.title == "My Note"
        assert read_note.metadata.tags == ["work", "project-x"]
        assert read_note.metadata.created == "2026-10-09"
        assert read_note.body == "This is the body content."

    def test_write_creates_md_file_in_notes_directory(self, tmp_path):
        """Test 2: Write creates a .md file in notes directory."""
        repo = NoteRepository(notes_dir=tmp_path)
        repo.write_note(
            filename="test-note.md",
            title="Test Note",
            body="Body here.",
            tags=["test"],
            created="2026-10-09",
        )
        assert (tmp_path / "test-note.md").exists()
        assert (tmp_path / "test-note.md").is_file()

    def test_write_with_invalid_filename_raises_error(self, tmp_path):
        """Test 3: Write with invalid filename raises InvalidTypeError."""
        repo = NoteRepository(notes_dir=tmp_path)
        with pytest.raises(InvalidTypeError):
            repo.write_note(
                filename="My Note!.md",
                title="Test",
                body="Body",
                tags=["test"],
                created="2026-10-09",
            )

    def test_write_with_path_traversal_raises_error(self, tmp_path):
        """Test 4: Write with path traversal in filename raises PathTraversalError."""
        repo = NoteRepository(notes_dir=tmp_path)
        with pytest.raises(PathTraversalError):
            repo.write_note(
                filename="../escape.md",
                title="Test",
                body="Body",
                tags=["test"],
                created="2026-10-09",
            )

    def test_atomic_write_creates_no_tmp_files(self, tmp_path):
        """Test 12: Atomic write creates no .tmp files after completion."""
        repo = NoteRepository(notes_dir=tmp_path)
        repo.write_note(
            filename="atomic-note.md",
            title="Atomic Note",
            body="Body content.",
            tags=["test"],
            created="2026-10-09",
        )
        # No .tmp files should remain
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0


class TestReadNote:
    """Tests for NoteRepository.read_note."""

    def test_read_nonexistent_note_raises_error(self, tmp_path):
        """Test 5: Read non-existent note raises NoteNotFoundError."""
        repo = NoteRepository(notes_dir=tmp_path)
        with pytest.raises(NoteNotFoundError):
            repo.read_note("nonexistent.md")

    def test_read_note_with_malformed_yaml_raises_error(self, tmp_path):
        """Test 14: Read note with malformed YAML raises MalformedYAMLError."""
        repo = NoteRepository(notes_dir=tmp_path)
        # Create a file with malformed YAML
        malformed_file = tmp_path / "bad-note.md"
        malformed_file.write_text(
            "---\n"
            'title: "Unclosed quote\n'
            "tags: [work]\n"
            'created: "2026-10-09"\n'
            "---\n"
            "Body content.\n",
            encoding="utf-8",
        )
        with pytest.raises(MalformedYAMLError):
            repo.read_note("bad-note.md")


class TestListNotes:
    """Tests for NoteRepository.list_notes."""

    def test_list_notes_returns_all_md_files_with_metadata(self, tmp_path):
        """Test 6: List notes returns all .md files with correct metadata."""
        repo = NoteRepository(notes_dir=tmp_path)
        repo.write_note(
            filename="note-a.md",
            title="Note A",
            body="Body A.",
            tags=["work"],
            created="2026-10-01",
        )
        repo.write_note(
            filename="note-b.md",
            title="Note B",
            body="Body B.",
            tags=["personal"],
            created="2026-10-05",
        )
        notes = repo.list_notes()
        assert len(notes) == 2
        titles = {n.title for n in notes}
        assert titles == {"Note A", "Note B"}

    def test_list_notes_ignores_non_md_files(self, tmp_path):
        """Test 7: List notes ignores non-.md files."""
        repo = NoteRepository(notes_dir=tmp_path)
        repo.write_note(
            filename="real-note.md",
            title="Real Note",
            body="Body.",
            tags=["test"],
            created="2026-10-09",
        )
        # Create non-.md files
        (tmp_path / "readme.txt").write_text("Not a note.")
        (tmp_path / "data.json").write_text('{"key": "value"}')
        notes = repo.list_notes()
        assert len(notes) == 1
        assert notes[0].title == "Real Note"

    def test_list_notes_on_empty_directory_returns_empty_list(self, tmp_path):
        """Test 8: List notes on empty directory returns empty list."""
        repo = NoteRepository(notes_dir=tmp_path)
        notes = repo.list_notes()
        assert notes == []


class TestDeleteNote:
    """Tests for NoteRepository.delete_note."""

    def test_delete_note_removes_file_from_disk(self, tmp_path):
        """Test 9: Delete note removes file from disk."""
        repo = NoteRepository(notes_dir=tmp_path)
        repo.write_note(
            filename="to-delete.md",
            title="To Delete",
            body="Body.",
            tags=["test"],
            created="2026-10-09",
        )
        assert (tmp_path / "to-delete.md").exists()
        repo.delete_note("to-delete.md")
        assert not (tmp_path / "to-delete.md").exists()

    def test_delete_nonexistent_note_raises_error(self, tmp_path):
        """Test 10: Delete non-existent note raises NoteNotFoundError."""
        repo = NoteRepository(notes_dir=tmp_path)
        with pytest.raises(NoteNotFoundError):
            repo.delete_note("nonexistent.md")


class TestUpdateNote:
    """Tests for NoteRepository.update_note."""

    def test_update_note_preserves_body_while_replacing_frontmatter(self, tmp_path):
        """Test 13: Update note preserves body content while replacing frontmatter."""
        repo = NoteRepository(notes_dir=tmp_path)
        repo.write_note(
            filename="update-me.md",
            title="Original Title",
            body="Original body content.",
            tags=["old-tag"],
            created="2026-10-01",
        )
        updated = repo.update_note(
            "update-me.md",
            title="Updated Title",
            tags=["new-tag"],
        )
        assert updated.metadata.title == "Updated Title"
        assert updated.metadata.tags == ["new-tag"]
        assert updated.body == "Original body content."
        assert updated.metadata.created == "2026-10-01"


class TestNotesDirEnvVar:
    """Tests for NOTES_DIR environment variable."""

    def test_notes_dir_env_var_configures_location(self, tmp_path, monkeypatch):
        """Test 11: NOTES_DIR env var configures notes directory location."""
        custom_dir = tmp_path / "custom-notes"
        monkeypatch.setenv("NOTES_DIR", str(custom_dir))
        repo = NoteRepository()
        assert repo.notes_dir == custom_dir.resolve()
        assert custom_dir.exists()

    def test_default_notes_dir_when_env_var_not_set(self, tmp_path, monkeypatch):
        """Default to ~/knowledge-base/notes when NOTES_DIR not set."""
        monkeypatch.delenv("NOTES_DIR", raising=False)
        repo = NoteRepository()
        expected = Path.home() / "knowledge-base" / "notes"
        assert repo.notes_dir == expected.resolve()
