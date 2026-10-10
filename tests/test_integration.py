"""Integration tests spanning all storage components."""

import os

import pytest

from kb_mcp.errors import PathTraversalError
from kb_mcp.storage import NoteRepository


class TestNoteLifecycle:
    """Tests for the complete note lifecycle: create -> read -> list -> update -> delete."""

    def test_full_lifecycle(self, repository):
        """Test 1: Full lifecycle — write -> read -> list -> update -> delete, verify data integrity."""
        # Write
        written = repository.write_note(
            filename="lifecycle-note.md",
            title="Lifecycle Note",
            body="Original body content.",
            tags=["test", "lifecycle"],
            created="2026-10-09",
        )
        assert written.filename == "lifecycle-note"
        assert written.metadata.title == "Lifecycle Note"
        assert written.body == "Original body content."

        # Read
        read = repository.read_note("lifecycle-note.md")
        assert read.metadata.title == "Lifecycle Note"
        assert read.metadata.tags == ["test", "lifecycle"]
        assert read.metadata.created == "2026-10-09"
        assert read.body == "Original body content."

        # List
        notes = repository.list_notes()
        assert len(notes) == 1
        assert notes[0].title == "Lifecycle Note"

        # Update
        updated = repository.update_note(
            "lifecycle-note.md",
            title="Updated Lifecycle Note",
            tags=["updated"],
        )
        assert updated.metadata.title == "Updated Lifecycle Note"
        assert updated.metadata.tags == ["updated"]
        assert updated.body == "Original body content."

        # Delete (title update renames lifecycle-note.md -> updated-lifecycle-note.md)
        repository.delete_note("updated-lifecycle-note.md")
        notes_after = repository.list_notes()
        assert len(notes_after) == 0

    def test_write_creates_file(self, repository, notes_dir):
        """Test 2: Write creates a .md file on disk."""
        repository.write_note(
            filename="disk-check.md",
            title="Disk Check",
            body="Body.",
            tags=["test"],
            created="2026-10-09",
        )
        assert (notes_dir / "disk-check.md").exists()
        assert (notes_dir / "disk-check.md").is_file()

    def test_read_returns_correct_metadata(self, repository):
        """Test 3: Read returns all frontmatter fields correctly."""
        repository.write_note(
            filename="metadata-check.md",
            title="Metadata Check",
            body="Body content.",
            tags=["alpha", "beta", "gamma"],
            created="2026-09-15",
        )
        note = repository.read_note("metadata-check.md")
        assert note.metadata.title == "Metadata Check"
        assert note.metadata.tags == ["alpha", "beta", "gamma"]
        assert note.metadata.created == "2026-09-15"
        assert note.body == "Body content."

    def test_list_returns_all_notes(self, repository):
        """Test 4: List returns all written notes."""
        repository.write_note("note-a.md", "Note A", "Body A.", ["work"], "2026-10-01")
        repository.write_note("note-b.md", "Note B", "Body B.", ["personal"], "2026-10-05")
        repository.write_note("note-c.md", "Note C", "Body C.", ["test"], "2026-10-09")
        notes = repository.list_notes()
        assert len(notes) == 3
        titles = {n.title for n in notes}
        assert titles == {"Note A", "Note B", "Note C"}

    def test_update_preserves_unspecified_fields(self, repository):
        """Test 5: Update only body, verify metadata unchanged."""
        repository.write_note(
            filename="preserve.md",
            title="Original Title",
            body="Original body.",
            tags=["original"],
            created="2026-10-01",
        )
        updated = repository.update_note("preserve.md", body="Updated body.")
        assert updated.metadata.title == "Original Title"
        assert updated.metadata.tags == ["original"]
        assert updated.metadata.created == "2026-10-01"
        assert updated.body == "Updated body."

    def test_delete_removes_file(self, repository, notes_dir):
        """Test 6: Delete removes file from disk."""
        repository.write_note("to-delete.md", "To Delete", "Body.", ["test"], "2026-10-09")
        assert (notes_dir / "to-delete.md").exists()
        repository.delete_note("to-delete.md")
        assert not (notes_dir / "to-delete.md").exists()


class TestEdgeCases:
    """Tests for edge cases: unicode, long content, BOM, malformed, empty dir."""

    def test_unicode_content(self, repository):
        """Test 7: Unicode content (Chinese, emoji) preserved exactly."""
        unicode_title = "Unicode Test"
        unicode_body = "Chinese: \u4f60\u597d\u4e16\u754c\U0001f600\U0001f4a1\nEmoji: \u2764\ufe0f\U0001f525"
        repository.write_note(
            filename="unicode-note.md",
            title=unicode_title,
            body=unicode_body,
            tags=["unicode", "\u4e2d\u6587"],
            created="2026-10-09",
        )
        note = repository.read_note("unicode-note.md")
        assert note.metadata.title == unicode_title
        assert note.body == unicode_body
        assert note.metadata.tags == ["unicode", "\u4e2d\u6587"]

    def test_long_content(self, repository):
        """Test 8: Very long body (10K+ chars) preserved exactly."""
        long_body = "A" * 10000 + "\n" + "B" * 5000
        repository.write_note(
            filename="long-note.md",
            title="Long Note",
            body=long_body,
            tags=["long"],
            created="2026-10-09",
        )
        note = repository.read_note("long-note.md")
        assert note.body == long_body
        assert len(note.body) == 15001

    def test_empty_directory(self, repository):
        """Test 9: List notes on empty directory returns empty list."""
        notes = repository.list_notes()
        assert notes == []

    def test_non_md_files_ignored(self, repository, notes_dir):
        """Test 10: Non-.md files are ignored by list_notes."""
        repository.write_note("real-note.md", "Real Note", "Body.", ["test"], "2026-10-09")
        (notes_dir / "readme.txt").write_text("Not a note.")
        (notes_dir / "data.json").write_text('{"key": "value"}')
        (notes_dir / "script.py").write_text("print('hello')")
        notes = repository.list_notes()
        assert len(notes) == 1
        assert notes[0].title == "Real Note"

    def test_malformed_note_skipped(self, repository, notes_dir):
        """Test 11: Malformed .md file is skipped by list_notes."""
        repository.write_note("good-note.md", "Good Note", "Body.", ["test"], "2026-10-09")
        (notes_dir / "bad-note.md").write_text(
            "---\n"
            'title: "Broken"\n'
            "tags: [unclosed\n"
            'created: "2026-10-09"\n'
            "---\n"
            "Body.\n",
            encoding="utf-8",
        )
        notes = repository.list_notes()
        assert len(notes) == 1
        assert notes[0].title == "Good Note"

    def test_bom_handling(self, repository, notes_dir):
        """Test 12: File with BOM character is parsed correctly."""
        bom_content = "\ufeff---\ntitle: \"BOM Note\"\ntags: [test]\ncreated: \"2026-10-09\"\n---\n\nBody.\n"
        (notes_dir / "bom-note.md").write_text(bom_content, encoding="utf-8")
        note = repository.read_note("bom-note.md")
        assert note.metadata.title == "BOM Note"
        assert note.metadata.tags == ["test"]
        assert note.body.strip() == "Body."

    def test_special_chars_in_title(self, repository):
        """Test 13: Title with special characters is preserved."""
        special_title = 'Special: "Quotes" & #Hashes'
        repository.write_note(
            filename="special-title.md",
            title=special_title,
            body="Body.",
            tags=["test"],
            created="2026-10-09",
        )
        note = repository.read_note("special-title.md")
        assert note.metadata.title == special_title


class TestSecurityIntegration:
    """Tests for security boundaries: path traversal, symlink escape, null bytes."""

    def test_traversal_in_read(self, repository):
        """Test 14: Path traversal in read_note raises PathTraversalError."""
        with pytest.raises(PathTraversalError):
            repository.read_note("../secret.md")

    def test_traversal_in_write(self, repository, tmp_path):
        """Test 15: Path traversal in write_note raises PathTraversalError, no file created."""
        with pytest.raises(PathTraversalError):
            repository.write_note("../evil.md", "Evil", "Body.", ["test"], "2026-10-09")
        # Verify no file created outside notes_dir
        assert not (tmp_path / "evil.md").exists()

    def test_traversal_in_delete(self, repository):
        """Test 16: Path traversal in delete_note raises PathTraversalError."""
        with pytest.raises(PathTraversalError):
            repository.delete_note("../important.md")

    def test_absolute_path_rejected(self, repository):
        """Test 17: Absolute path raises PathTraversalError."""
        with pytest.raises(PathTraversalError):
            repository.read_note("/etc/passwd")

    def test_null_bytes_rejected(self, repository):
        """Test 18: Null bytes in filename raise PathTraversalError."""
        with pytest.raises(PathTraversalError):
            repository.read_note("note\x00.md")

    def test_symlink_escape_rejected(self, repository, notes_dir, tmp_path):
        """Test 19: Symlink pointing outside notes_dir raises PathTraversalError."""
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        outside_file = outside_dir / "secret.txt"
        outside_file.write_text("secret data")

        symlink_path = notes_dir / "escape.md"
        try:
            os.symlink(outside_file, symlink_path)
        except (OSError, NotImplementedError):
            pytest.skip("Symlink creation not supported on this platform")

        with pytest.raises(PathTraversalError):
            repository.read_note("escape.md")

    def test_no_tmp_files_after_write(self, repository, notes_dir):
        """Test 20: No .tmp files remain after write_note completes."""
        repository.write_note("clean-write.md", "Clean", "Body.", ["test"], "2026-10-09")
        tmp_files = list(notes_dir.glob("*.tmp"))
        assert len(tmp_files) == 0
