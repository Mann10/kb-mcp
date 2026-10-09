"""Path validation and filename sanitization for note storage."""

import re
from pathlib import Path
from urllib.parse import unquote

from .errors import InvalidTypeError, PathTraversalError

# Safe filename: lowercase alphanumeric, hyphens, underscores, must end with .md
SAFE_FILENAME = re.compile(r'^[a-z0-9][a-z0-9_-]*\.md$')


def validate_filename(filename: str) -> str:
    """Validate filename matches safe naming convention.

    Args:
        filename: The filename to validate (e.g., "my-note.md").

    Returns:
        The validated filename.

    Raises:
        InvalidTypeError: If filename contains unsafe characters.
    """
    if not SAFE_FILENAME.match(filename):
        raise InvalidTypeError(
            filename,
            "filename",
            "safe lowercase-with-hyphens .md",
            filename,
        )
    return filename


def validate_path(notes_dir: Path, relative_path: str) -> Path:
    """Validate and resolve a relative path within the notes directory.

    Args:
        notes_dir: The base notes directory.
        relative_path: Relative path within the notes directory.

    Returns:
        Resolved absolute path.

    Raises:
        PathTraversalError: If the path escapes the notes directory.
    """
    # Decode URL-encoded paths (e.g., %2e%2e%2f → ../)
    relative_path = unquote(relative_path)

    # Reject absolute paths (D-11)
    if Path(relative_path).is_absolute():
        raise PathTraversalError(
            relative_path,
            f"Absolute paths not allowed: {relative_path}",
        )

    # Reject null bytes
    if "\x00" in relative_path:
        raise PathTraversalError(
            relative_path,
            f"Null bytes not allowed in path: {relative_path}",
        )

    # Reject .. segments
    if ".." in Path(relative_path).parts:
        raise PathTraversalError(
            relative_path,
            f"Path traversal detected: {relative_path} contains '..' segment",
        )

    # Resolve the path
    notes_dir_resolved = notes_dir.resolve()
    candidate = (notes_dir_resolved / relative_path).resolve()

    # Verify containment (D-09)
    if not candidate.is_relative_to(notes_dir_resolved):
        raise PathTraversalError(
            relative_path,
            f"Path traversal detected: {relative_path} resolves outside notes directory",
        )

    return candidate
