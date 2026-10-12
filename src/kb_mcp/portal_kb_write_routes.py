"""KB write BFF routes (Phase 12-02 task 1).

Six D-13-gated endpoints mirroring v1 ``write_tools`` boundary validation,
rename, and idempotent tag semantics over HTTP:

- ``POST /api/notes/create`` — create incl. validation + exists 409
- ``POST /api/notes/create-from-template`` — template pre-fill create
- ``PUT /api/notes/update`` — update incl. title-rename returning new_stem
- ``DELETE /api/notes/delete`` — delete with actor trail
- ``POST /api/notes/add-tags`` / ``POST /api/notes/remove-tags`` — idempotent tags

Gating (D-13, locked): every route runs ``require_user`` (401
``PORTAL_INVALID_MESSAGE``) then ``has_write_access(email)`` (403
``{"success": false, "message": "Write access required."}``). Email comes
from the validated JWT only — never from client-sent fields.

Parity strategy (RESEARCH 2, deliberate): the BFF does NOT call the
``require_write``-decorated ``write_tools`` functions (they need an MCP
``token`` + ``_store``; the BFF has a Supabase JWT). It replicates the exact
validation order and byte-identical messages, then calls the shared repo
interface (``write_note`` / ``update_note`` / ``delete_note``) with
``actor=user.email`` so both filesystem and Supabase backends work.

Conventions (do not reshape): ``portal_auth`` imported as a module so tests
can monkeypatch ``validate_portal_jwt`` on both references; CORS via
``portal_cors._cors_headers`` / ``handle_options``; explicit ``OPTIONS`` per
route; message-only errors, no stack traces.
Import-safe: zero I/O and zero required env at import.
"""

import datetime
import re

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from kb_mcp import portal_auth
from kb_mcp.backend import get_note_repository, get_template_store
from kb_mcp.errors import InvalidTypeError, NoteNotFoundError
from kb_mcp.portal_cors import _cors_headers, handle_options
from kb_mcp.portal_kb_gate import has_write_access
from kb_mcp.server import mcp
from kb_mcp.validation import validate_filename

WRITE_DENIED = "Write access required."


def _deny_401(request: Request) -> JSONResponse:
    """Fail-closed 401 with the locked portal message."""
    return JSONResponse(
        {"success": False, "message": portal_auth.PORTAL_INVALID_MESSAGE},
        status_code=401,
        headers=_cors_headers(request),
    )


def _deny_403(request: Request) -> JSONResponse:
    """Fail-closed 403 with the locked D-13 denial (message-only)."""
    return JSONResponse(
        {"success": False, "message": WRITE_DENIED},
        status_code=403,
        headers=_cors_headers(request),
    )


def _gate(request: Request):
    """Return (user, denial_response). denial_response is None when allowed."""
    user = portal_auth.require_user(request)
    if user is None:
        return None, _deny_401(request)
    if not has_write_access(user.email):
        return None, _deny_403(request)
    return user, None


async def _read_json(request: Request) -> dict:
    """Parse a JSON body; ``{}`` on any failure (untrusted input, fail-closed)."""
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _slugify_title(title: str) -> str | None:
    """Slug a display title to a safe ``*.md`` filename, or None if empty."""
    s = title.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9_-]", "", s)
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip("-_")
    if not s:
        return None
    return s + ".md"


def _resolve_stem(repo, name: str) -> str | None:
    """Resolve a user-supplied name to a canonical stem (v1 parity)."""
    if not isinstance(name, str):
        return None
    wanted_raw = name.strip()
    if wanted_raw.lower().endswith(".md"):
        wanted_raw = wanted_raw[:-3]
    wanted = wanted_raw.strip()
    if not wanted:
        return None
    try:
        stem_map = {stem.lower(): stem for stem in repo.list_stems()}
    except OSError:
        stem_map = {}
    hit = stem_map.get(wanted.lower())
    if hit is not None:
        return hit
    lowered = wanted.lower()
    for stem in sorted(stem_map.values()):
        try:
            candidate = repo.read_note(stem + ".md")
        except Exception:
            continue
        if (candidate.metadata.title or "").strip().lower() == lowered:
            return stem
    return None


def _note_payload(stem: str, note) -> dict:
    """BFF note object shared by all write success payloads."""
    return {
        "stem": stem,
        "title": note.metadata.title,
        "tags": list(note.metadata.tags),
        "created": note.metadata.created,
    }


def _validate_tag_list(tags) -> str | None:
    """v1 _validate_tag_list parity: None when valid, else invalid message."""
    if (
        not isinstance(tags, list)
        or any(not isinstance(t, str) for t in tags)
        or any(len(t) >= 100 for t in tags)
    ):
        return "Invalid tags: must be a list of strings each under 100 characters."
    for t in tags:
        if not t.strip():
            return "Invalid tags: must be a list of strings each under 100 characters."
    return None


@mcp.custom_route("/api/notes/create", methods=["POST"])
async def kb_create(request: Request) -> Response:
    """Create a note; collisions are a structured 409 (v1 parity)."""
    user, denied = _gate(request)
    if denied is not None:
        return denied
    data = await _read_json(request)
    repo = get_note_repository()
    title = data.get("title")
    tags = data.get("tags")
    created = data.get("created")
    body = data.get("body", "")
    if not isinstance(title, str) or not title.strip():
        return JSONResponse(
            {"success": False, "message": "Invalid title: must be a non-empty string."},
            status_code=400,
            headers=_cors_headers(request),
        )
    display_title = title.strip()
    normalized_tags = [] if tags is None else tags
    if (
        not isinstance(normalized_tags, list)
        or any(not isinstance(t, str) for t in normalized_tags)
        or any(len(t) >= 100 for t in normalized_tags)
    ):
        return JSONResponse(
            {"success": False, "message": "Invalid tags: must be a list of strings each under 100 characters."},
            status_code=400,
            headers=_cors_headers(request),
        )
    if created is None:
        created = datetime.date.today().isoformat()
    if not isinstance(created, str):
        return JSONResponse(
            {"success": False, "message": f"Invalid created: must be an ISO date (YYYY-MM-DD), got '{created}'."},
            status_code=400,
            headers=_cors_headers(request),
        )
    try:
        created = datetime.date.fromisoformat(created.strip()).isoformat()
    except ValueError:
        return JSONResponse(
            {"success": False, "message": f"Invalid created: must be an ISO date (YYYY-MM-DD), got '{created}'."},
            status_code=400,
            headers=_cors_headers(request),
        )
    if not isinstance(body, str):
        return JSONResponse(
            {"success": False, "message": "Invalid body: must be a string."},
            status_code=400,
            headers=_cors_headers(request),
        )
    filename = _slugify_title(display_title)
    if filename is None:
        return JSONResponse(
            {"success": False, "message": "Invalid title: must slugify to a safe filename."},
            status_code=400,
            headers=_cors_headers(request),
        )
    try:
        validate_filename(filename)
    except InvalidTypeError:
        return JSONResponse(
            {"success": False, "message": "Invalid title: must slugify to a safe filename."},
            status_code=400,
            headers=_cors_headers(request),
        )
    if repo.stem_exists(filename[:-3]):
        stem = filename[:-3]
        return JSONResponse(
            {"success": False, "message": f"Note '{display_title}' already exists as {stem}."},
            status_code=409,
            headers=_cors_headers(request),
        )
    try:
        note = repo.write_note(
            filename, display_title, body, list(normalized_tags), created,
            actor=user.email,
        )
    except (InvalidTypeError, ValueError) as e:
        return JSONResponse(
            {"success": False, "message": f"Invalid note field: {e}."},
            status_code=400,
            headers=_cors_headers(request),
        )
    return JSONResponse(
        {
            "success": True,
            "note": _note_payload(note.filename, note),
            "filename": note.filename,
            "message": f"Note '{note.metadata.title}' created as {note.filename}.",
        },
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/notes/create", methods=["OPTIONS"])
async def kb_create_options(request: Request) -> Response:
    """Preflight for /api/notes/create."""
    return handle_options(request)


@mcp.custom_route("/api/notes/create-from-template", methods=["POST"])
async def kb_create_from_template(request: Request) -> Response:
    """Create a note from a template skeleton with override merge (v1 parity)."""
    user, denied = _gate(request)
    if denied is not None:
        return denied
    data = await _read_json(request)
    repo = get_note_repository()
    tstore = get_template_store()
    template = data.get("template")
    title = data.get("title")
    body = data.get("body")
    tags = data.get("tags")
    created = data.get("created")
    norm = template.strip().lower() if isinstance(template, str) else ""
    if tstore.get(norm) is None:
        return JSONResponse(
            {"success": False, "message": f"Unknown template '{template}'. Valid templates: {', '.join(tstore.names())}."},
            status_code=404,
            headers=_cors_headers(request),
        )
    spec = tstore.get(norm)
    effective_body = body if body is not None else spec["body_skeleton"]
    effective_tags = list(spec["default_tags"])
    if not isinstance(title, str) or not title.strip():
        return JSONResponse(
            {"success": False, "message": "Invalid title: must be a non-empty string."},
            status_code=400,
            headers=_cors_headers(request),
        )
    display_title = title.strip()
    if tags is not None:
        if (
            not isinstance(tags, list)
            or any(not isinstance(t, str) for t in tags)
            or any(len(t) >= 100 for t in tags)
        ):
            return JSONResponse(
                {"success": False, "message": "Invalid tags: must be a list of strings each under 100 characters."},
                status_code=400,
                headers=_cors_headers(request),
            )
        for t in tags:
            if not t.strip():
                return JSONResponse(
                    {"success": False, "message": "Invalid tags: must be a list of strings each under 100 characters."},
                    status_code=400,
                    headers=_cors_headers(request),
                )
        seen = {t.strip().lower() for t in effective_tags}
        for raw in tags:
            s = raw.strip()
            if s.lower() in seen:
                continue
            effective_tags.append(s)
            seen.add(s.lower())
    if (
        not isinstance(effective_tags, list)
        or any(not isinstance(t, str) for t in effective_tags)
        or any(len(t) >= 100 for t in effective_tags)
    ):
        return JSONResponse(
            {"success": False, "message": "Invalid tags: must be a list of strings each under 100 characters."},
            status_code=400,
            headers=_cors_headers(request),
        )
    for t in effective_tags:
        if not t.strip():
            return JSONResponse(
                {"success": False, "message": "Invalid tags: must be a list of strings each under 100 characters."},
                status_code=400,
                headers=_cors_headers(request),
            )
    if created is None:
        created = datetime.date.today().isoformat()
    if not isinstance(created, str):
        return JSONResponse(
            {"success": False, "message": f"Invalid created: must be an ISO date (YYYY-MM-DD), got '{created}'."},
            status_code=400,
            headers=_cors_headers(request),
        )
    try:
        created = datetime.date.fromisoformat(created.strip()).isoformat()
    except ValueError:
        return JSONResponse(
            {"success": False, "message": f"Invalid created: must be an ISO date (YYYY-MM-DD), got '{created}'."},
            status_code=400,
            headers=_cors_headers(request),
        )
    if not isinstance(effective_body, str):
        return JSONResponse(
            {"success": False, "message": "Invalid body: must be a string."},
            status_code=400,
            headers=_cors_headers(request),
        )
    filename = _slugify_title(display_title)
    if filename is None:
        return JSONResponse(
            {"success": False, "message": "Invalid title: must slugify to a safe filename."},
            status_code=400,
            headers=_cors_headers(request),
        )
    try:
        validate_filename(filename)
    except InvalidTypeError:
        return JSONResponse(
            {"success": False, "message": "Invalid title: must slugify to a safe filename."},
            status_code=400,
            headers=_cors_headers(request),
        )
    if repo.stem_exists(filename[:-3]):
        stem = filename[:-3]
        return JSONResponse(
            {"success": False, "message": f"Note '{display_title}' already exists as {stem}."},
            status_code=409,
            headers=_cors_headers(request),
        )
    try:
        note = repo.write_note(
            filename, display_title, effective_body, list(effective_tags), created,
            actor=user.email,
        )
    except (InvalidTypeError, ValueError) as e:
        return JSONResponse(
            {"success": False, "message": f"Invalid note field: {e}."},
            status_code=400,
            headers=_cors_headers(request),
        )
    return JSONResponse(
        {
            "success": True,
            "note": _note_payload(note.filename, note),
            "filename": note.filename,
            "message": f"Note '{note.metadata.title}' created from '{norm}' template as {note.filename}.",
        },
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/notes/create-from-template", methods=["OPTIONS"])
async def kb_create_from_template_options(request: Request) -> Response:
    """Preflight for /api/notes/create-from-template."""
    return handle_options(request)


@mcp.custom_route("/api/notes/update", methods=["PUT"])
async def kb_update(request: Request) -> Response:
    """Update content/metadata; title-change renames and returns new_stem (v1 parity)."""
    user, denied = _gate(request)
    if denied is not None:
        return denied
    data = await _read_json(request)
    repo = get_note_repository()
    stem = data.get("stem")
    if stem is None or (isinstance(stem, str) and not stem.strip()):
        stem = data.get("title")
    lookup = stem if isinstance(stem, str) else stem
    new_title = data.get("new_title")
    body = data.get("body")
    tags = data.get("tags")
    created = data.get("created")
    if new_title is None and body is None and tags is None and created is None:
        real_stem = _resolve_stem(repo, lookup) if isinstance(lookup, str) else None
        if real_stem is None:
            return JSONResponse(
                {"success": False, "message": f"Note '{lookup}' not found."},
                status_code=404,
                headers=_cors_headers(request),
            )
        try:
            note = repo.read_note(real_stem + ".md")
        except NoteNotFoundError:
            return JSONResponse(
                {"success": False, "message": f"Note '{lookup}' not found."},
                status_code=404,
                headers=_cors_headers(request),
            )
        return JSONResponse(
            {
                "success": True,
                "note": _note_payload(note.filename, note),
                "new_stem": note.filename,
                "message": f"No changes — note '{lookup}' unchanged.",
            },
            headers=_cors_headers(request),
        )
    if tags is not None:
        if (
            not isinstance(tags, list)
            or any(not isinstance(t, str) for t in tags)
            or any(len(t) >= 100 for t in tags)
        ):
            return JSONResponse(
                {"success": False, "message": "Invalid tags: must be a list of strings each under 100 characters."},
                status_code=400,
                headers=_cors_headers(request),
            )
    if created is not None:
        if not isinstance(created, str):
            return JSONResponse(
                {"success": False, "message": f"Invalid created: must be YYYY-MM-DD, got '{created}'."},
                status_code=400,
                headers=_cors_headers(request),
            )
        try:
            datetime.date.fromisoformat(created.strip())
        except ValueError:
            return JSONResponse(
                {"success": False, "message": f"Invalid created: must be YYYY-MM-DD, got '{created}'."},
                status_code=400,
                headers=_cors_headers(request),
            )
    if new_title is not None:
        if not isinstance(new_title, str) or not new_title.strip():
            return JSONResponse(
                {"success": False, "message": "Invalid title: must be a non-empty string."},
                status_code=400,
                headers=_cors_headers(request),
            )
        if _slugify_title(new_title) is None:
            return JSONResponse(
                {"success": False, "message": f"Invalid title: '{new_title}' cannot form a safe filename."},
                status_code=400,
                headers=_cors_headers(request),
            )
    if body is not None and not isinstance(body, str):
        return JSONResponse(
            {"success": False, "message": "Invalid body: must be a string."},
            status_code=400,
            headers=_cors_headers(request),
        )
    real_stem = _resolve_stem(repo, lookup) if isinstance(lookup, str) else None
    if real_stem is None:
        return JSONResponse(
            {"success": False, "message": f"Note '{lookup}' not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    if new_title is not None:
        slug_file = _slugify_title(new_title)
        slug = slug_file[:-3] if slug_file is not None else None
        if slug is not None and slug != real_stem and repo.stem_exists(slug):
            return JSONResponse(
                {"success": False, "message": f"Note '{new_title.strip()}' already exists as '{slug}'. Rename rejected."},
                status_code=409,
                headers=_cors_headers(request),
            )
    try:
        note = repo.update_note(
            real_stem + ".md",
            title=(new_title.strip() if new_title is not None else None),
            body=body,
            tags=(list(tags) if tags is not None else None),
            created=created,
            actor=user.email,
        )
    except NoteNotFoundError:
        return JSONResponse(
            {"success": False, "message": f"Note '{lookup}' not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    except (InvalidTypeError, ValueError) as e:
        return JSONResponse(
            {"success": False, "message": f"Invalid note field: {e}."},
            status_code=400,
            headers=_cors_headers(request),
        )
    except FileExistsError as e:
        return JSONResponse(
            {"success": False, "message": f"Note '{new_title}' already exists. Rename rejected. ({e})"},
            status_code=409,
            headers=_cors_headers(request),
        )
    return JSONResponse(
        {
            "success": True,
            "note": _note_payload(note.filename, note),
            "new_stem": note.filename,
            "message": f"Updated note '{note.metadata.title}'.",
        },
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/notes/update", methods=["OPTIONS"])
async def kb_update_options(request: Request) -> Response:
    """Preflight for /api/notes/update."""
    return handle_options(request)


@mcp.custom_route("/api/notes/delete", methods=["DELETE"])
async def kb_delete(request: Request) -> Response:
    """Delete a note by stem/title; missing notes are a structured 404."""
    user, denied = _gate(request)
    if denied is not None:
        return denied
    data = await _read_json(request)
    repo = get_note_repository()
    stem = data.get("stem")
    if stem is None or (isinstance(stem, str) and not stem.strip()):
        stem = data.get("title")
    real_stem = _resolve_stem(repo, stem) if isinstance(stem, str) else None
    if real_stem is None:
        return JSONResponse(
            {"success": False, "message": f"Note '{stem}' not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    try:
        repo.delete_note(real_stem + ".md", actor=user.email)
    except NoteNotFoundError:
        return JSONResponse(
            {"success": False, "message": f"Note '{stem}' not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    return JSONResponse(
        {"success": True, "filename": real_stem, "stem": real_stem, "message": f"Note '{real_stem}' deleted."},
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/notes/delete", methods=["OPTIONS"])
async def kb_delete_options(request: Request) -> Response:
    """Preflight for /api/notes/delete."""
    return handle_options(request)


@mcp.custom_route("/api/notes/add-tags", methods=["POST"])
async def kb_add_tags(request: Request) -> Response:
    """Idempotent tag merge; repeat calls are No-changes success (v1 parity)."""
    user, denied = _gate(request)
    if denied is not None:
        return denied
    data = await _read_json(request)
    repo = get_note_repository()
    stem = data.get("stem")
    if stem is None or (isinstance(stem, str) and not stem.strip()):
        stem = data.get("title")
    tags = data.get("tags")
    invalid = _validate_tag_list(tags)
    if invalid is not None:
        return JSONResponse(
            {"success": False, "message": "Invalid tags: must be a list of strings each under 100 characters."},
            status_code=400,
            headers=_cors_headers(request),
        )
    incoming = [t.strip() for t in tags]
    real_stem = _resolve_stem(repo, stem) if isinstance(stem, str) else None
    if real_stem is None:
        return JSONResponse(
            {"success": False, "message": f"Note '{stem}' not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    try:
        note = repo.read_note(real_stem + ".md")
    except NoteNotFoundError:
        return JSONResponse(
            {"success": False, "message": f"Note '{stem}' not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    existing = list(note.metadata.tags or [])
    seen = {t.strip().lower() for t in existing}
    merged = list(existing)
    for s in incoming:
        if s.lower() in seen:
            continue
        merged.append(s)
        seen.add(s.lower())
    if merged == existing:
        return JSONResponse(
            {
                "success": True,
                "note": _note_payload(note.filename, note),
                "message": f"No changes — note '{note.metadata.title}' already has those tags.",
            },
            headers=_cors_headers(request),
        )
    try:
        updated = repo.update_note(real_stem + ".md", tags=merged, actor=user.email)
    except NoteNotFoundError:
        return JSONResponse(
            {"success": False, "message": f"Note '{stem}' not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    except (InvalidTypeError, ValueError) as e:
        return JSONResponse(
            {"success": False, "message": f"Invalid note field: {e}."},
            status_code=400,
            headers=_cors_headers(request),
        )
    return JSONResponse(
        {
            "success": True,
            "note": _note_payload(updated.filename, updated),
            "message": f"Added {len(merged) - len(existing)} tag(s) to '{updated.metadata.title}'.",
        },
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/notes/add-tags", methods=["OPTIONS"])
async def kb_add_tags_options(request: Request) -> Response:
    """Preflight for /api/notes/add-tags."""
    return handle_options(request)


@mcp.custom_route("/api/notes/remove-tags", methods=["POST"])
async def kb_remove_tags(request: Request) -> Response:
    """Idempotent tag removal; missing tags are No-changes success (v1 parity)."""
    user, denied = _gate(request)
    if denied is not None:
        return denied
    data = await _read_json(request)
    repo = get_note_repository()
    stem = data.get("stem")
    if stem is None or (isinstance(stem, str) and not stem.strip()):
        stem = data.get("title")
    tags = data.get("tags")
    invalid = _validate_tag_list(tags)
    if invalid is not None:
        return JSONResponse(
            {"success": False, "message": "Invalid tags: must be a list of strings each under 100 characters."},
            status_code=400,
            headers=_cors_headers(request),
        )
    incoming = [t.strip() for t in tags]
    real_stem = _resolve_stem(repo, stem) if isinstance(stem, str) else None
    if real_stem is None:
        return JSONResponse(
            {"success": False, "message": f"Note '{stem}' not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    try:
        note = repo.read_note(real_stem + ".md")
    except NoteNotFoundError:
        return JSONResponse(
            {"success": False, "message": f"Note '{stem}' not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    existing = list(note.metadata.tags or [])
    drop = {s.lower() for s in incoming}
    kept = [t for t in existing if t.strip().lower() not in drop]
    if kept == existing:
        return JSONResponse(
            {
                "success": True,
                "note": _note_payload(note.filename, note),
                "message": f"No changes — note '{note.metadata.title}' already lacks those tags.",
            },
            headers=_cors_headers(request),
        )
    try:
        updated = repo.update_note(real_stem + ".md", tags=kept, actor=user.email)
    except NoteNotFoundError:
        return JSONResponse(
            {"success": False, "message": f"Note '{stem}' not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    except (InvalidTypeError, ValueError) as e:
        return JSONResponse(
            {"success": False, "message": f"Invalid note field: {e}."},
            status_code=400,
            headers=_cors_headers(request),
        )
    return JSONResponse(
        {
            "success": True,
            "note": _note_payload(updated.filename, updated),
            "message": f"Removed {len(existing) - len(kept)} tag(s) from '{updated.metadata.title}'.",
        },
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/notes/remove-tags", methods=["OPTIONS"])
async def kb_remove_tags_options(request: Request) -> Response:
    """Preflight for /api/notes/remove-tags."""
    return handle_options(request)
