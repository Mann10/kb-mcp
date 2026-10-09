"""Custom exception classes for storage errors."""


class PathTraversalError(Exception):
    """Raised when a path escapes the notes directory."""

    def __init__(self, path: str, message: str = ""):
        self.path = path
        self.message = message or f"Path traversal detected: {path}"
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class NoteNotFoundError(Exception):
    """Raised when a note file doesn't exist."""

    def __init__(self, filename: str):
        self.filename = filename
        super().__init__(f"Note not found: {filename}")

    def __str__(self) -> str:
        return f"Note not found: {self.filename}"


class MalformedYAMLError(Exception):
    """Raised when YAML parsing fails."""

    def __init__(self, filename: str, original_error: str):
        self.filename = filename
        self.original_error = original_error
        super().__init__(f"Note '{filename}' has invalid frontmatter: {original_error}")

    def __str__(self) -> str:
        return f"Note '{self.filename}' has invalid frontmatter: {self.original_error}"


class MissingFieldError(Exception):
    """Raised when a required field is missing."""

    def __init__(self, filename: str, field: str):
        self.filename = filename
        self.field = field
        super().__init__(f"Note '{filename}' is missing required field: {field}")

    def __str__(self) -> str:
        return f"Note '{self.filename}' is missing required field: {self.field}"


class InvalidTypeError(Exception):
    """Raised when a field has the wrong type."""

    def __init__(self, filename: str, field: str, expected_type: str, actual_type: str):
        self.filename = filename
        self.field = field
        self.expected_type = expected_type
        self.actual_type = actual_type
        super().__init__(
            f"Note '{filename}' field '{field}' has invalid type: "
            f"expected {expected_type}, got {actual_type}"
        )

    def __str__(self) -> str:
        return (
            f"Note '{self.filename}' field '{self.field}' has invalid type: "
            f"expected {self.expected_type}, got {self.actual_type}"
        )


class FileIOError(Exception):
    """Raised on I/O failure."""

    def __init__(self, filename: str, operation: str, original_error: str):
        self.filename = filename
        self.operation = operation
        self.original_error = original_error
        super().__init__(f"Failed to {operation} note '{filename}': {original_error}")

    def __str__(self) -> str:
        return f"Failed to {self.operation} note '{self.filename}': {self.original_error}"


class AuthenticationError(Exception):
    """Raised when a token is missing, unknown, revoked, or expired."""

    def __init__(self, message: str = "Invalid or missing token."):
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class AuthorizationError(Exception):
    """Raised when a valid token lacks the scope for an operation."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message
