"""Knowledge Base MCP server foundation (Phase 9, Plan 09-01).

FastMCP app with streamable-http transport only, fail-fast startup, and
thin tool wrappers over the Phase 5-8 gated tools.

Transport auth, rate limiting, audit logging, and error mapping land in
Plan 09-03; this module only plumbs ``token`` + ``_store`` through to the
unchanged ``require_read`` / ``require_write`` decorators (D-08).
"""

import logging
import os
from pathlib import Path

from fastmcp import FastMCP

from kb_mcp.auth import TokenStore

logger = logging.getLogger("kb_mcp.server")

mcp = FastMCP("KnowledgeBase")


def resolve_notes_dir(raw: str | None = None) -> Path:
    """Resolve the notes directory: explicit arg > NOTES_DIR env > default."""
    if raw:
        return Path(raw)
    env_dir = os.environ.get("NOTES_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.home() / "knowledge-base" / "notes"


def ensure_notes_dir(path: Path) -> Path:
    """Fail fast when NOTES_DIR is missing or unwritable (D-06).

    Never creates the directory — a missing dir is an operator error with
    a clear message, not something to silently auto-create.
    """
    if not path.exists():
        raise SystemExit(f"NOTES_DIR '{path}' is missing: create it or set NOTES_DIR to an existing writable directory.")
    if not os.access(path, os.W_OK):
        raise SystemExit(f"NOTES_DIR '{path}' is not writable: fix permissions or set NOTES_DIR to a writable directory.")
    return path


def get_request_token() -> str:
    """Return the raw client token from the current request context.

    Stub for Plan 09-01: transport auth is wired in Plan 09-03 (D-07/D-09).
    Until then every wrapper fails closed instead of passing anything through.
    """
    raise RuntimeError("transport auth not wired")


# Imported lazily inside wrappers so module import stays light and nothing
# at import time depends on transport state.
from kb_mcp.read_tools import get_note as _get_note_gated
from kb_mcp.read_tools import get_tags as _get_tags_gated
from kb_mcp.read_tools import list_notes as _list_notes_gated
from kb_mcp.read_tools import search_notes as _search_notes_gated
from kb_mcp.write_tools import add_tags as _add_tags_gated
from kb_mcp.write_tools import create_from_template as _create_from_template_gated
from kb_mcp.write_tools import create_note as _create_note_gated
from kb_mcp.write_tools import delete_note as _delete_note_gated
from kb_mcp.write_tools import remove_tags as _remove_tags_gated
from kb_mcp.write_tools import update_note as _update_note_gated


@mcp.tool()
def search_notes(
    query: str = "",
    limit: int = 10,
    tag: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Search notes by keyword across body + title + stem + tags."""
    raw = get_request_token()
    store = TokenStore.load()
    return _search_notes_gated(query, limit, tag, date_from, date_to, token=raw, _store=store)


@mcp.tool()
def get_note(title: str) -> dict:
    """Retrieve a single note by case-insensitive title/stem lookup."""
    raw = get_request_token()
    store = TokenStore.load()
    return _get_note_gated(title, token=raw, _store=store)


@mcp.tool()
def list_notes() -> dict:
    """List all notes with metadata only (no bodies)."""
    raw = get_request_token()
    store = TokenStore.load()
    return _list_notes_gated(token=raw, _store=store)


@mcp.tool()
def get_tags() -> dict:
    """Browse tags across all notes, frequency-sorted."""
    raw = get_request_token()
    store = TokenStore.load()
    return _get_tags_gated(token=raw, _store=store)


@mcp.tool()
def create_note(
    title: str,
    body: str = "",
    tags: list[str] | None = None,
    created: str | None = None,
) -> dict:
    """Create a new note; reject collisions with a structured exists-error."""
    raw = get_request_token()
    store = TokenStore.load()
    return _create_note_gated(title, body, tags, created, token=raw, _store=store)


@mcp.tool()
def update_note(
    title: str,
    new_title: str | None = None,
    body: str | None = None,
    tags: list[str] | None = None,
    created: str | None = None,
) -> dict:
    """Update content/metadata of an existing note; rename on new_title."""
    raw = get_request_token()
    store = TokenStore.load()
    return _update_note_gated(title, new_title, body, tags, created, token=raw, _store=store)


@mcp.tool()
def delete_note(title: str) -> dict:
    """Delete a note by title/stem."""
    raw = get_request_token()
    store = TokenStore.load()
    return _delete_note_gated(title, token=raw, _store=store)


@mcp.tool()
def add_tags(title: str, tags: list[str]) -> dict:
    """Add tags to an existing note (idempotent merge)."""
    raw = get_request_token()
    store = TokenStore.load()
    return _add_tags_gated(title, tags, token=raw, _store=store)


@mcp.tool()
def remove_tags(title: str, tags: list[str]) -> dict:
    """Remove tags from an existing note (idempotent merge)."""
    raw = get_request_token()
    store = TokenStore.load()
    return _remove_tags_gated(title, tags, token=raw, _store=store)


@mcp.tool()
def create_from_template(
    template: str,
    title: str,
    body: str | None = None,
    tags: list[str] | None = None,
    created: str | None = None,
) -> dict:
    """Create a new note from a template skeleton with override merge."""
    raw = get_request_token()
    store = TokenStore.load()
    return _create_from_template_gated(template, title, body, tags, created, token=raw, _store=store)


def serve(host: str = "0.0.0.0", port: int = 8000, notes_dir: str | None = None) -> None:
    """Start the MCP server on streamable-http after fail-fast checks (D-01/D-06)."""
    resolved = ensure_notes_dir(resolve_notes_dir(notes_dir))
    from kb_mcp.read_tools import configure_default_repo as configure_read_repo
    from kb_mcp.storage import NoteRepository
    from kb_mcp.write_tools import configure_default_repo as configure_write_repo

    repo = NoteRepository(notes_dir=resolved)
    configure_read_repo(repo)
    configure_write_repo(repo)
    logger.info("transport=streamable-http host=%s port=%s notes_dir=%s", host, port, resolved)
    mcp.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    serve()
