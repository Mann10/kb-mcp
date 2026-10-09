"""Tests for YAML frontmatter parsing with type validation."""

import pytest

from kb_mcp.errors import (
    MalformedYAMLError,
    MissingFieldError,
    InvalidTypeError,
)
from kb_mcp.parsing import parse_frontmatter, split_frontmatter


class TestSplitFrontmatter:
    """Tests for split_frontmatter function."""

    def test_valid_frontmatter_splits_correctly(self):
        """Test 1: Valid frontmatter parses correctly."""
        content = '---\ntitle: "Test Note"\ntags: [work, project-x]\ncreated: "2026-10-09"\n---\n\n# Test Note\n\nBody content here.\n'
        yaml_text, body = split_frontmatter(content)
        assert "title" in yaml_text
        assert "Test Note" in yaml_text
        assert body.strip() == "# Test Note\n\nBody content here."

    def test_missing_closing_delimiter_raises_error(self):
        """Test 3: Missing closing --- delimiter raises MalformedYAMLError."""
        content = '---\ntitle: "Test Note"\ntags: [work]\ncreated: "2026-10-09"\n\nBody without closing delimiter.\n'
        with pytest.raises(MalformedYAMLError):
            split_frontmatter(content)

    def test_body_content_preserved_exactly(self):
        """Test 8: Body content after frontmatter is preserved exactly."""
        content = '---\ntitle: "Test"\ntags: [a]\ncreated: "2026-01-01"\n---\n\n# Heading\n\nParagraph with **bold** text.\n\n- List item 1\n- List item 2\n'
        yaml_text, body = split_frontmatter(content)
        assert body == '\n# Heading\n\nParagraph with **bold** text.\n\n- List item 1\n- List item 2\n'


class TestParseFrontmatter:
    """Tests for parse_frontmatter function."""

    def test_valid_frontmatter_parses_correctly(self):
        """Test 1: Valid frontmatter parses correctly — title is string, tags is list of strings, created is string."""
        content = '---\ntitle: "Meeting Notes"\ntags: [work, project-x]\ncreated: "2026-10-09"\n---\n\n# Meeting Notes\n\nContent here.\n'
        metadata, body = parse_frontmatter(content, "meeting-notes.md")
        assert metadata.title == "Meeting Notes"
        assert metadata.tags == ["work", "project-x"]
        assert metadata.created == "2026-10-09"
        assert isinstance(metadata.title, str)
        assert isinstance(metadata.tags, list)
        assert all(isinstance(t, str) for t in metadata.tags)
        assert isinstance(metadata.created, str)

    def test_yaml_boolean_strings_preserved(self):
        """Test 2: Frontmatter with tags: [on, off] preserves strings (not booleans)."""
        content = '---\ntitle: "Test"\ntags: [on, off]\ncreated: "2026-10-09"\n---\n\nBody.\n'
        metadata, body = parse_frontmatter(content, "test.md")
        assert metadata.tags == ["on", "off"]
        assert all(isinstance(t, str) for t in metadata.tags)

    def test_invalid_yaml_raises_malformed_error(self):
        """Test 4: Invalid YAML syntax raises MalformedYAMLError with filename in message."""
        content = '---\ntitle: "Test"\ntags: [unclosed\ncreated: "2026-10-09"\n---\n\nBody.\n'
        with pytest.raises(MalformedYAMLError) as exc_info:
            parse_frontmatter(content, "bad-note.md")
        assert "bad-note.md" in str(exc_info.value)

    def test_missing_required_field_raises_error(self):
        """Test 5: Missing required field (title) raises MissingFieldError with field name."""
        content = '---\ntags: [work]\ncreated: "2026-10-09"\n---\n\nBody.\n'
        with pytest.raises(MissingFieldError) as exc_info:
            parse_frontmatter(content, "missing-title.md")
        assert "title" in str(exc_info.value)
        assert "missing-title.md" in str(exc_info.value)

    def test_wrong_type_raises_invalid_type_error(self):
        """Test 6: Wrong type (tags as string instead of list) raises InvalidTypeError."""
        content = '---\ntitle: "Test"\ntags: "work, project-x"\ncreated: "2026-10-09"\n---\n\nBody.\n'
        with pytest.raises(InvalidTypeError) as exc_info:
            parse_frontmatter(content, "wrong-type.md")
        assert "tags" in str(exc_info.value)
        assert "wrong-type.md" in str(exc_info.value)

    def test_bom_character_handled_correctly(self):
        """Test 7: BOM character at start of file is handled correctly."""
        content = '\ufeff---\ntitle: "BOM Test"\ntags: [test]\ncreated: "2026-10-09"\n---\n\nBody.\n'
        metadata, body = parse_frontmatter(content, "bom-note.md")
        assert metadata.title == "BOM Test"
        assert metadata.tags == ["test"]

    def test_empty_frontmatter_raises_missing_field(self):
        """Test 9: Empty frontmatter (just ---/---) raises MissingFieldError for all required fields."""
        content = '---\n---\n\nBody.\n'
        with pytest.raises(MissingFieldError) as exc_info:
            parse_frontmatter(content, "empty.md")
        assert "title" in str(exc_info.value)

    def test_extra_unknown_fields_accepted(self):
        """Test 10: Frontmatter with extra unknown fields is accepted (forward compatibility)."""
        content = '---\ntitle: "Test"\ntags: [work]\ncreated: "2026-10-09"\nauthor: "Alice"\ncustom_field: "value"\n---\n\nBody.\n'
        metadata, body = parse_frontmatter(content, "extra-fields.md")
        assert metadata.title == "Test"
        assert metadata.tags == ["work"]
        assert metadata.created == "2026-10-09"
