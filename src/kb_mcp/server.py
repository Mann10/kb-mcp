"""Knowledge Base MCP server (Phase 9).

FastMCP app with streamable-http transport only, fail-fast startup, and
thin tool wrappers over the Phase 5-8 gated tools.

Transport auth (D-07 header extraction, D-09 fail-closed), rate limiting
(D-11..D-14), audit logging (D-15/D-16/D-18), and client-safe error mapping
(D-17) are wired here in Plan 09-03. The ``require_read`` / ``require_write``
decorators are reused unchanged (D-08): wrappers inject ``token`` + ``_store``
so verify -> scope-check -> invoke semantics stay identical.
"""

import logging
import os
from collections.abc import Callable
from pathlib import Path

from fastmcp import FastMCP

from kb_mcp.audit import log_denial, log_read, log_write, mask_token
from kb_mcp.auth import TokenStore
from kb_mcp.backend import get_token_store, use_supabase
from kb_mcp.supabase_audit import audit_write_db
from kb_mcp.supabase_auth import SupabaseTokenStore
from kb_mcp.errors import AuthenticationError, AuthorizationError
from kb_mcp.middleware import INVALID_TOKEN_MESSAGE, verify_token
from kb_mcp.rate_limit import RATE_LIMIT_MESSAGE, check_rate_limit, owner_key

logger = logging.getLogger("kb_mcp.server")

mcp = FastMCP("KnowledgeBase")

from kb_mcp import portal_routes  # noqa: F401  (BFF custom_route registration, D-10)
from kb_mcp import portal_token_routes  # noqa: F401  (BFF user token routes, Phase 11-01)


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


def get_request_token() -> str | None:
    """Return the raw client token from the current request's ``x-api-token`` header.

    D-07: the token travels via the ``x-api-token`` HTTP header only — tool
    schemas stay clean (no token argument). D-09: return ``None`` when ANY
    link in the context chain is missing (no context, no request, no header)
    so the caller denies fail-closed with ``INVALID_TOKEN_MESSAGE``.

    Deliberate deviation from the reference (``C:\\personal\\CD\\MCP\\server.py``
    ``AuthMiddleware``): the reference logged "Authentication skipped" and
    CONTINUED down the chain when no HTTP request context was available.
    Phase 9 does the opposite per D-09 — missing context never passes
    through; it denies. Every ``return None`` below is that fail-closed rule.
    """
    # Attempt 1: FastMCP per-request context var (bound for the duration of
    # each request handler via ``bind_request_context``). This is the runtime
    # equivalent of the researched path
    # ``context.fastmcp_context.request_context.request.headers.get(...)``.
    try:
        from fastmcp.server.dependencies import fastmcp_request_ctx

        request_ctx = fastmcp_request_ctx.get()
        request = getattr(request_ctx, "request", None) if request_ctx is not None else None
        headers = getattr(request, "headers", None)
        if headers is not None:
            try:
                token = headers.get("x-api-token")
            except Exception:
                token = None
            if token:
                return token
            try:
                for name, value in headers.items():
                    if name.lower() == "x-api-token" and value:
                        return value
            except Exception:
                pass
    except Exception:
        pass
    # Attempt 2: full ``Context`` object (covers hosts that bind ``_current_context``
    # rather than the request-context var).
    try:
        from fastmcp.server.context import _current_context

        ctx = _current_context.get()
        request_context = getattr(ctx, "request_context", None) if ctx is not None else None
        request = getattr(request_context, "request", None) if request_context is not None else None
        headers = getattr(request, "headers", None)
        if headers is not None:
            try:
                token = headers.get("x-api-token")
            except Exception:
                token = None
            if token:
                return token
    except Exception:
        pass
    # Attempt 3: ``get_http_request()`` helper (request-context var first,
    # then the HTTP-context fallback used during early middleware stages).
    try:
        from fastmcp.server.dependencies import get_http_request

        request = get_http_request()
        headers = getattr(request, "headers", None)
        if headers is not None:
            try:
                token = headers.get("x-api-token")
            except Exception:
                token = None
            if token:
                return token
    except Exception:
        pass
    return None


def _invoke(
    tool_name: str,
    gated_fn: Callable[..., dict],
    store: TokenStore | SupabaseTokenStore,
    kwargs: dict,
    is_write: bool,
    filename_of: Callable[[dict], str] | None = None,
) -> dict:
    """Run one tool call through the verify -> rate-limit -> invoke pipeline.

    Order is locked (threat model T-09-09..T-09-12): header token is verified
    BEFORE anything else; the rate check is keyed on the verified owner
    (never the IP, never an anonymous bucket); only verified calls reach the
    gated tool, whose unchanged decorators re-check scope (defense in depth,
    D-08). Denials return the locked strings verbatim (D-10); unexpected
    errors return structured payloads with the server-side stack trace kept in
    logs only (D-17); every log call carries a masked token (D-18).
    """
    raw = get_request_token()
    entry = verify_token(raw, store)
    if entry is None:
        log_denial("auth", None, tool_name, mask_token(raw))
        return {"success": False, "message": INVALID_TOKEN_MESSAGE}
    user = owner_key(entry)
    if not check_rate_limit(user):
        log_denial("rate-limit", user, tool_name, mask_token(raw))
        return {"success": False, "message": RATE_LIMIT_MESSAGE}
    try:
        if is_write:
            result = gated_fn(**kwargs, token=raw, _store=store, actor=user)
        else:
            result = gated_fn(**kwargs, token=raw, _store=store)
    except (AuthenticationError, AuthorizationError) as e:
        log_denial("auth", user, tool_name, mask_token(raw))
        return {"success": False, "message": str(e)}
    except Exception as e:
        logger.exception("tool %s failed for user=%s", tool_name, user)
        return {"success": False, "message": f"Internal error in {tool_name}: {e}."}
    if is_write:
        if filename_of is not None and isinstance(result, dict):
            try:
                filename = filename_of(result)
            except Exception:
                filename = tool_name
        else:
            filename = tool_name
        if use_supabase():
            audit_write_db(user, tool_name, filename)
        else:
            log_write(user, tool_name, filename)
    else:
        log_read(tool_name)
    return result


# Imported lazily inside wrappers so module import stays light and nothing
# at import time depends on transport state.
from kb_mcp.read_tools import get_note as _get_note_gated
from kb_mcp.read_tools import get_tags as _get_tags_gated
from kb_mcp.read_tools import list_notes as _list_notes_gated
from kb_mcp.read_tools import search_notes as _search_notes_gated
from kb_mcp.templates import create_template as _create_template_gated
from kb_mcp.templates import delete_template as _delete_template_gated
from kb_mcp.templates import list_templates as _list_templates_gated
from kb_mcp.templates import update_template as _update_template_gated
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
    return _invoke(
        "search_notes",
        _search_notes_gated,
        get_token_store(),
        {"query": query, "limit": limit, "tag": tag, "date_from": date_from, "date_to": date_to},
        is_write=False,
    )


@mcp.tool()
def get_note(title: str) -> dict:
    """Retrieve a single note by case-insensitive title/stem lookup."""
    return _invoke("get_note", _get_note_gated, get_token_store(), {"title": title}, is_write=False)


@mcp.tool()
def list_notes() -> dict:
    """List all notes with metadata only (no bodies)."""
    return _invoke("list_notes", _list_notes_gated, get_token_store(), {}, is_write=False)


@mcp.tool()
def get_tags() -> dict:
    """Browse tags across all notes, frequency-sorted."""
    return _invoke("get_tags", _get_tags_gated, get_token_store(), {}, is_write=False)


@mcp.tool()
def create_note(
    title: str,
    body: str = "",
    tags: list[str] | None = None,
    created: str | None = None,
) -> dict:
    """Create a new note; reject collisions with a structured exists-error."""
    return _invoke(
        "create_note",
        _create_note_gated,
        get_token_store(),
        {"title": title, "body": body, "tags": tags, "created": created},
        is_write=True,
        filename_of=lambda r: r.get("filename", "create_note"),
    )


@mcp.tool()
def update_note(
    title: str,
    new_title: str | None = None,
    body: str | None = None,
    tags: list[str] | None = None,
    created: str | None = None,
) -> dict:
    """Update content/metadata of an existing note; rename on new_title."""
    return _invoke(
        "update_note",
        _update_note_gated,
        get_token_store(),
        {"title": title, "new_title": new_title, "body": body, "tags": tags, "created": created},
        is_write=True,
        filename_of=lambda r: r.get("filename", "update_note"),
    )


@mcp.tool()
def delete_note(title: str) -> dict:
    """Delete a note by title/stem."""
    return _invoke(
        "delete_note",
        _delete_note_gated,
        get_token_store(),
        {"title": title},
        is_write=True,
        filename_of=lambda r: r.get("filename", "delete_note"),
    )


@mcp.tool()
def add_tags(title: str, tags: list[str]) -> dict:
    """Add tags to an existing note (idempotent merge)."""
    return _invoke(
        "add_tags",
        _add_tags_gated,
        get_token_store(),
        {"title": title, "tags": tags},
        is_write=True,
        filename_of=lambda r: r.get("filename", "add_tags"),
    )


@mcp.tool()
def remove_tags(title: str, tags: list[str]) -> dict:
    """Remove tags from an existing note (idempotent merge)."""
    return _invoke(
        "remove_tags",
        _remove_tags_gated,
        get_token_store(),
        {"title": title, "tags": tags},
        is_write=True,
        filename_of=lambda r: r.get("filename", "remove_tags"),
    )


@mcp.tool()
def create_from_template(
    template: str,
    title: str,
    body: str | None = None,
    tags: list[str] | None = None,
    created: str | None = None,
) -> dict:
    """Create a new note from a template skeleton with override merge."""
    return _invoke(
        "create_from_template",
        _create_from_template_gated,
        get_token_store(),
        {"template": template, "title": title, "body": body, "tags": tags, "created": created},
        is_write=True,
        filename_of=lambda r: r.get("filename", "create_from_template"),
    )


@mcp.tool()
def list_templates() -> dict:
    """List all note templates with skeletons and default tags."""
    return _invoke("list_templates", _list_templates_gated, get_token_store(), {}, is_write=False)


@mcp.tool()
def create_template(
    name: str,
    body_skeleton: str = "",
    default_tags: list[str] | None = None,
) -> dict:
    """Create a note template; reject duplicates with a structured exists-error."""
    return _invoke(
        "create_template",
        _create_template_gated,
        get_token_store(),
        {"name": name, "body_skeleton": body_skeleton, "default_tags": default_tags},
        is_write=True,
        filename_of=lambda r: r.get("name", "create_template"),
    )


@mcp.tool()
def update_template(
    name: str,
    body_skeleton: str | None = None,
    default_tags: list[str] | None = None,
) -> dict:
    """Partially update a note template; no-op update is success."""
    return _invoke(
        "update_template",
        _update_template_gated,
        get_token_store(),
        {"name": name, "body_skeleton": body_skeleton, "default_tags": default_tags},
        is_write=True,
        filename_of=lambda r: r.get("name", "update_template"),
    )


@mcp.tool()
def delete_template(name: str) -> dict:
    """Delete a note template by name."""
    return _invoke(
        "delete_template",
        _delete_template_gated,
        get_token_store(),
        {"name": name},
        is_write=True,
        filename_of=lambda r: r.get("name", "delete_template"),
    )


def serve(host: str = "0.0.0.0", port: int = 8000, notes_dir: str | None = None, portal_origins: str | None = None) -> None:
    """Start the MCP server on streamable-http after fail-fast checks (D-01/D-06)."""
    from kb_mcp.backend import get_note_repository
    from kb_mcp.read_tools import configure_default_repo as configure_read_repo
    from kb_mcp.write_tools import configure_default_repo as configure_write_repo

    if use_supabase():
        # No local notes directory needed — state lives in Supabase.
        repo = get_note_repository()
        resolved = "supabase"
    else:
        resolved = ensure_notes_dir(resolve_notes_dir(notes_dir))
        from kb_mcp.storage import NoteRepository

        repo = NoteRepository(notes_dir=resolved)
    configure_read_repo(repo)
    configure_write_repo(repo)
    logger.info("transport=streamable-http host=%s port=%s notes_dir=%s", host, port, resolved)
    # Portal CORS (D-14): Starlette CORSMiddleware when the installed fastmcp
    # run() accepts a middleware kwarg; otherwise skip silently (Horizon path
    # relies on the manual Origin echo in portal_routes).
    try:
        import inspect as _inspect

        _sig = _inspect.signature(mcp.run)
        _params = _sig.parameters
        _accepts_mw = "middleware" in _params or any(
            p.kind == _inspect.Parameter.VAR_KEYWORD for p in _params.values()
        )
    except Exception:
        _accepts_mw = False
    if _accepts_mw:
        try:
            from starlette.middleware import Middleware as _Middleware
            from starlette.middleware.cors import CORSMiddleware as _CORSMiddleware

            _raw = portal_origins if portal_origins is not None else os.environ.get("PORTAL_ORIGINS", "")
            _parsed = [o.strip() for o in _raw.split(",") if o.strip()]
            _middleware = [
                _Middleware(
                    _CORSMiddleware,
                    allow_origins=_parsed,
                    allow_methods=["GET", "OPTIONS"],
                    allow_headers=["Authorization", "Content-Type"],
                    max_age=600,
                )
            ]
            mcp.run(transport="streamable-http", host=host, port=port, middleware=_middleware)
        except Exception as e:
            logger.warning("portal middleware skipped (%s); using manual CORS echo", type(e).__name__)
            mcp.run(transport="streamable-http", host=host, port=port)
    else:
        mcp.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    serve()
