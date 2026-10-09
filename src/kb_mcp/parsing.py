"""YAML frontmatter parsing with type validation."""

from ruamel.yaml import YAML

from .errors import MalformedYAMLError, MissingFieldError, InvalidTypeError
from .models import NoteMetadata


def split_frontmatter(content: str) -> tuple[str, str]:
    """Split content into YAML frontmatter text and body.

    Args:
        content: Raw file content (may include BOM).

    Returns:
        Tuple of (yaml_text, body).

    Raises:
        MalformedYAMLError: If frontmatter delimiters are missing.
    """
    # Strip BOM if present
    content = content.lstrip('\ufeff')

    # Check content starts with ---\n
    if not content.startswith('---\n'):
        raise MalformedYAMLError("", "missing opening --- delimiter")

    # Find closing --- line
    lines = content.split('\n')
    closing_index = None
    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            closing_index = i
            break

    if closing_index is None:
        raise MalformedYAMLError("", "missing closing --- delimiter")

    # Extract YAML text between delimiters
    yaml_text = '\n'.join(lines[1:closing_index])

    # Extract body after closing delimiter (preserve exact content)
    body = '\n'.join(lines[closing_index + 1:])

    return yaml_text, body


def parse_frontmatter(content: str, filename: str = "") -> tuple[NoteMetadata, str]:
    """Parse YAML frontmatter and return NoteMetadata and body.

    Args:
        content: Raw file content.
        filename: Filename for error messages.

    Returns:
        Tuple of (NoteMetadata, body).

    Raises:
        MalformedYAMLError: If YAML parsing fails.
        MissingFieldError: If required field is missing.
        InvalidTypeError: If field has wrong type.
    """
    yaml_text, body = split_frontmatter(content)

    # Parse YAML using ruamel.yaml
    yaml = YAML()
    yaml.preserve_quotes = True

    try:
        data = yaml.load(yaml_text)
    except Exception as e:
        raise MalformedYAMLError(filename, str(e))

    # Handle empty frontmatter
    if data is None:
        raise MissingFieldError(filename, "title")

    # Validate required fields exist
    required_fields = ["title", "tags", "created"]
    for field in required_fields:
        if field not in data:
            raise MissingFieldError(filename, field)

    # Validate types
    if not isinstance(data["title"], str):
        raise InvalidTypeError(filename, "title", "str", type(data["title"]).__name__)

    if not isinstance(data["tags"], list):
        raise InvalidTypeError(filename, "tags", "list", type(data["tags"]).__name__)

    for i, tag in enumerate(data["tags"]):
        if not isinstance(tag, str):
            raise InvalidTypeError(filename, f"tags[{i}]", "str", type(tag).__name__)

    if not isinstance(data["created"], str):
        raise InvalidTypeError(filename, "created", "str", type(data["created"]).__name__)

    # Create NoteMetadata (pydantic handles additional validation)
    metadata = NoteMetadata.model_validate(data)

    return metadata, body
