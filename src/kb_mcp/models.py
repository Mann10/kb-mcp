"""Pydantic models for note validation."""

import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class NoteMetadata(BaseModel):
    """Metadata extracted from YAML frontmatter."""

    model_config = ConfigDict(strict=True)

    title: str
    tags: list[str]
    created: str

    @field_validator("title")
    @classmethod
    def title_must_be_non_empty(cls, v: str) -> str:
        """Validate title is non-empty after stripping whitespace."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("title must be non-empty")
        return stripped

    @field_validator("tags")
    @classmethod
    def tags_must_be_valid_strings(cls, v: list[str]) -> list[str]:
        """Validate all tags are strings under 100 characters."""
        for tag in v:
            if not isinstance(tag, str):
                raise ValueError(f"all tags must be strings, got {type(tag).__name__}")
            if len(tag) >= 100:
                raise ValueError(f"tag '{tag}' must be less than 100 characters")
        return v

    @field_validator("created")
    @classmethod
    def created_must_be_iso_date(cls, v: str) -> str:
        """Validate created is an ISO 8601 date string (YYYY-MM-DD)."""
        try:
            datetime.date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"created must be an ISO 8601 date (YYYY-MM-DD), got '{v}'")
        return v


class Note(BaseModel):
    """Complete note with metadata and body."""

    filename: str
    metadata: NoteMetadata
    body: str

    def to_markdown(self) -> str:
        """Return the full note as a string with YAML frontmatter delimiters."""
        tags_str = ", ".join(self.metadata.tags)
        return (
            f"---\n"
            f"title: \"{self.metadata.title}\"\n"
            f"tags: [{tags_str}]\n"
            f"created: \"{self.metadata.created}\"\n"
            f"---\n"
            f"{self.body}"
        )
