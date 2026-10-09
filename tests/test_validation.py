"""Tests for path validation and filename sanitization."""

import os
from pathlib import Path

import pytest

from kb_mcp.errors import InvalidTypeError, PathTraversalError
from kb_mcp.validation import SAFE_FILENAME, validate_filename, validate_path


class TestValidatePath:
    """Tests for validate_path function."""

    def test_valid_relative_path_resolves_within_notes_dir(self, tmp_path):
        """Test 1: Valid relative path 'my-note.md' resolves correctly within notes dir."""
        notes_dir = tmp_path / "notes"
        notes_dir.mkdir()
        result = validate_path(notes_dir, "my-note.md")
        assert result == (notes_dir / "my-note.md").resolve()
        assert result.is_absolute()

    def test_path_with_dotdot_raises_traversal_error(self, tmp_path):
        """Test 2: Path with '..' segment ('../etc/passwd') raises PathTraversalError."""
        notes_dir = tmp_path / "notes"
        notes_dir.mkdir()
        with pytest.raises(PathTraversalError):
            validate_path(notes_dir, "../etc/passwd")

    def test_absolute_path_raises_traversal_error(self, tmp_path):
        """Test 3: Absolute path ('/etc/passwd') raises PathTraversalError."""
        notes_dir = tmp_path / "notes"
        notes_dir.mkdir()
        with pytest.raises(PathTraversalError):
            validate_path(notes_dir, "/etc/passwd")

    def test_encoded_traversal_raises_traversal_error(self, tmp_path):
        """Test 4: Path with encoded traversal ('%2e%2e%2f') raises PathTraversalError."""
        notes_dir = tmp_path / "notes"
        notes_dir.mkdir()
        with pytest.raises(PathTraversalError):
            validate_path(notes_dir, "%2e%2e%2fetc%2fpasswd")

    def test_symlink_pointing_outside_raises_traversal_error(self, tmp_path):
        """Test 5: Symlink pointing outside notes dir raises PathTraversalError."""
        notes_dir = tmp_path / "notes"
        notes_dir.mkdir()
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        outside_file = outside_dir / "secret.txt"
        outside_file.write_text("secret")

        symlink_path = notes_dir / "escape.md"
        try:
            os.symlink(outside_file, symlink_path)
        except (OSError, NotImplementedError):
            pytest.skip("Symlink creation not supported on this platform")

        with pytest.raises(PathTraversalError):
            validate_path(notes_dir, "escape.md")

    def test_null_bytes_in_path_raises_traversal_error(self, tmp_path):
        """Test 6: Null bytes in path raise PathTraversalError."""
        notes_dir = tmp_path / "notes"
        notes_dir.mkdir()
        with pytest.raises(PathTraversalError):
            validate_path(notes_dir, "note\x00.md")


class TestValidateFilename:
    """Tests for validate_filename function."""

    def test_valid_filename_passes(self):
        """Test 7: Valid filename 'my-note-title.md' passes validation."""
        result = validate_filename("my-note-title.md")
        assert result == "my-note-title.md"

    def test_invalid_filename_with_uppercase_space_special_char(self):
        """Test 8: Invalid filename 'My Note!.md' fails validation."""
        with pytest.raises(InvalidTypeError):
            validate_filename("My Note!.md")

    def test_filename_with_path_traversal_fails(self):
        """Test 9: Filename with path traversal ('../note.md') fails validation."""
        with pytest.raises(InvalidTypeError):
            validate_filename("../note.md")

    def test_non_md_extension_fails(self):
        """Test 10: Non-.md extension ('note.txt') fails validation."""
        with pytest.raises(InvalidTypeError):
            validate_filename("note.txt")


class TestSafeFilenameRegex:
    """Tests for SAFE_FILENAME regex pattern."""

    def test_regex_matches_valid_filenames(self):
        """SAFE_FILENAME matches valid lowercase-with-hyphens .md filenames."""
        assert SAFE_FILENAME.match("my-note.md")
        assert SAFE_FILENAME.match("note123.md")
        assert SAFE_FILENAME.match("a.md")
        assert SAFE_FILENAME.match("my_note-title.md")

    def test_regex_rejects_invalid_filenames(self):
        """SAFE_FILENAME rejects filenames with unsafe characters."""
        assert not SAFE_FILENAME.match("My Note.md")
        assert not SAFE_FILENAME.match("note.txt")
        assert not SAFE_FILENAME.match("../note.md")
        assert not SAFE_FILENAME.match("-note.md")
        assert not SAFE_FILENAME.match("note.md.bak")
