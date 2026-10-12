"""KB read BFF routes (Phase 12-01 task 2).

Six ``require_user``-gated endpoints re-exposing v1 read semantics over
HTTP, plus the D-13 ``can_write`` probe every later plan imports:

- ``GET /api/notes/search`` — keyword + tag + date AND combo, v1 rank order
- ``GET /api/notes/list`` — created-ascending metadata-only entries
- ``GET /api/notes/get`` — single note full content by stem or title
- ``GET /api/notes/tags`` — frequency-sorted tag catalog
- ``GET /api/notes/templates`` — template catalog for the D-09 picker
- ``GET /api/notes/can_write`` — ``{can_write: bool}``, never token data

Parity strategy (RESEARCH 1, deliberate): the BFF does NOT call the
``require_read``-decorated ``read_tools`` functions (they need an MCP
``token`` + ``_store``; the BFF has a Supabase JWT). It imports the shared
constants and the repo via per-call dispatch, then replicates the exact
ranking/snippet/filter loop from ``read_tools.search_notes`` so messages
stay byte-identical.

Conventions (do not reshape): ``portal_auth`` imported as a module so tests
can monkeypatch ``validate_portal_jwt`` on both references; CORS via
``portal_cors._cors_headers`` / ``handle_options``; 401
``PORTAL_INVALID_MESSAGE`` message-only; explicit ``OPTIONS`` per route.
Import-safe: zero I/O and zero required env at import.
"""

import datetime

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from kb_mcp import portal_auth
from kb_mcp.backend import get_note_repository, get_template_store
from kb_mcp.portal_cors import _cors_headers, handle_options
from kb_mcp.portal_kb_gate import has_write_access
from kb_mcp.read_tools import DEFAULT_LIMIT, MAX_LIMIT, SNIPPET_CONTEXT
from kb_mcp.server import mcp


def _deny_401(request: Request) -> JSONResponse:
    """Fail-closed 401 with the locked portal message."""
    return JSONResponse(
        {"success": False, "message": portal_auth.PORTAL_INVALID_MESSAGE},
        status_code=401,
        headers=_cors_headers(request),
    )


def _build_snippet(body: str, q: str, hit_index: int) -> str:
    """Keyword-in-context snippet around the first body match (v1 parity)."""
    start = max(0, hit_index - SNIPPET_CONTEXT)
    end = min(len(body), hit_index + len(q) + SNIPPET_CONTEXT)
    snippet = " ".join(body[start:end].split())
    if start > 0:
        snippet = "\u2026" + snippet
    if end < len(body):
        snippet = snippet + "\u2026"
    return snippet


def _search_core(query: str, tag, date_from, date_to, limit_raw) -> dict:
    """Replicate read_tools.search_notes semantics exactly (v1 parity)."""
    repo = get_note_repository()
    try:
        limit = int(limit_raw)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    if limit <= 0:
        limit = DEFAULT_LIMIT
    else:
        limit = min(limit, MAX_LIMIT)
    q = query.strip().lower() if isinstance(query, str) else ""
    tag_active = isinstance(tag, str) and bool(tag.strip())
    df_raw = date_from.strip() if isinstance(date_from, str) and date_from.strip() else None
    dt_raw = date_to.strip() if isinstance(date_to, str) and date_to.strip() else None
    for bound in (df_raw, dt_raw):
        if bound is not None:
            try:
                datetime.date.fromisoformat(bound)
            except ValueError:
                return {"results": [], "message": f"Invalid date filter value '{bound}'. Use YYYY-MM-DD."}
    if df_raw is not None:
        df_raw = datetime.date.fromisoformat(df_raw).isoformat()
    if dt_raw is not None:
        dt_raw = datetime.date.fromisoformat(dt_raw).isoformat()
    date_active = df_raw is not None or dt_raw is not None
    if not q and not tag_active and not date_active:
        return {"results": [], "message": f"No notes found matching '{query}'."}
    try:
        stems = repo.list_stems()
    except OSError:
        stems = []
    ranked: list[tuple[int, str, dict]] = []
    for stem in stems:
        try:
            note = repo.read_note(stem + ".md")
        except Exception:
            continue
        body = note.body or ""
        title = note.metadata.title or ""
        tags = list(note.metadata.tags or [])
        hit_index = body.lower().find(q) if q else -1
        body_hit = hit_index >= 0
        title_hit = q in title.lower() or q in stem.lower()
        tags_hit = any(q in t.lower() for t in tags)
        tag_hit = True if not tag_active else any(t.strip().lower() == tag.strip().lower() for t in tags)
        if tag_active and not tag_hit:
            continue
        if q and not (body_hit or title_hit or tags_hit):
            continue
        created = note.metadata.created
        if df_raw is not None and created < df_raw:
            continue
        if dt_raw is not None and created > dt_raw:
            continue
        if body_hit:
            rank = 0
            snippet = _build_snippet(body, q, hit_index)
        elif q:
            rank = 1 if title_hit else 2
            snippet = " ".join(body[:200].split())
        else:
            rank = 0
            snippet = " ".join(body[:200].split())
        ranked.append(
            (
                rank,
                note.metadata.created,
                {
                    "stem": stem,
                    "title": title,
                    "tags": tags,
                    "created": note.metadata.created,
                    "snippet": snippet,
                },
            )
        )
    ranked.sort(key=lambda item: (item[0], item[1]))
    results = [payload for _, _, payload in ranked[:limit]]
    parts = []
    if tag_active:
        parts.append(f"tag='{tag.strip()}'")
    if df_raw is not None:
        parts.append(f"date_from='{df_raw}'")
    if dt_raw is not None:
        parts.append(f"date_to='{dt_raw}'")
    if not parts:
        if not results:
            return {"results": [], "message": f"No notes found matching '{query}'."}
        count = len(results)
        return {
            "results": results,
            "message": f"Found {count} note(s) matching '{query}'.",
        }
    suffix = " [" + ", ".join(parts) + "]."
    if not results:
        if q:
            return {"results": [], "message": f"No notes found matching '{query}'" + suffix}
        return {"results": [], "message": "No notes found" + suffix}
    count = len(results)
    if q:
        return {
            "results": results,
            "message": f"Found {count} note(s) matching '{query}'" + suffix,
        }
    return {
        "results": results,
        "message": f"Found {count} note(s)" + suffix,
    }


def _resolve_stem(repo, name: str):
    """Stem-map first, then display-title fallback (v1 _resolve_stem parity)."""
    try:
        stem_map = {stem.lower(): stem for stem in repo.list_stems()}
    except OSError:
        stem_map = {}
    real_stem = stem_map.get(name.lower())
    if real_stem is None:
        wanted = name.lower()
        for stem in sorted(stem_map.values()):
            try:
                candidate = repo.read_note(stem + ".md")
            except Exception:
                continue
            if (candidate.metadata.title or "").strip().lower() == wanted:
                real_stem = stem
                break
    return real_stem


@mcp.custom_route("/api/notes/search", methods=["GET"])
async def kb_search(request: Request) -> Response:
    """Keyword + tag + date search with v1 ranking and snippets."""
    user = portal_auth.require_user(request)
    if user is None:
        return _deny_401(request)
    params = request.query_params
    payload = _search_core(
        params.get("q", ""),
        params.get("tag"),
        params.get("date_from"),
        params.get("date_to"),
        params.get("limit"),
    )
    return JSONResponse(payload, headers=_cors_headers(request))


@mcp.custom_route("/api/notes/search", methods=["OPTIONS"])
async def kb_search_options(request: Request) -> Response:
    """Preflight for /api/notes/search."""
    return handle_options(request)


@mcp.custom_route("/api/notes/list", methods=["GET"])
async def kb_list(request: Request) -> Response:
    """Created-ascending metadata-only note list (no bodies)."""
    user = portal_auth.require_user(request)
    if user is None:
        return _deny_401(request)
    repo = get_note_repository()
    pairs = []
    for stem in repo.list_stems():
        try:
            note = repo.read_note(stem + ".md")
        except Exception:
            continue
        pairs.append((note.metadata, stem))
    pairs.sort(key=lambda item: item[0].created)
    if not pairs:
        return JSONResponse({"notes": [], "message": "No notes found."}, headers=_cors_headers(request))
    notes = [
        {"stem": stem, "title": m.title, "tags": list(m.tags), "created": m.created}
        for m, stem in pairs
    ]
    return JSONResponse(
        {"notes": notes, "message": f"Found {len(notes)} note(s)."},
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/notes/list", methods=["OPTIONS"])
async def kb_list_options(request: Request) -> Response:
    """Preflight for /api/notes/list."""
    return handle_options(request)


@mcp.custom_route("/api/notes/get", methods=["GET"])
async def kb_get(request: Request) -> Response:
    """Full note content by stem or display title (deep-linkable)."""
    user = portal_auth.require_user(request)
    if user is None:
        return _deny_401(request)
    params = request.query_params
    raw = params.get("stem")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raw = params.get("title")
    if not isinstance(raw, str):
        return JSONResponse(
            {"success": False, "message": f"Note '{raw}' not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    name = raw.strip()
    if name.lower().endswith(".md"):
        name = name[:-3]
    if not name:
        return JSONResponse(
            {"success": False, "message": f"Note '{raw}' not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    repo = get_note_repository()
    real_stem = _resolve_stem(repo, name)
    if real_stem is None:
        return JSONResponse(
            {"success": False, "message": f"Note '{raw}' not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    try:
        note = repo.read_note(real_stem + ".md")
    except Exception:
        return JSONResponse(
            {"success": False, "message": f"Note '{raw}' not found."},
            status_code=404,
            headers=_cors_headers(request),
        )
    return JSONResponse(
        {
            "success": True,
            "note": {
                "stem": real_stem,
                "title": note.metadata.title,
                "tags": list(note.metadata.tags),
                "created": note.metadata.created,
                "body": note.body,
            },
        },
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/notes/get", methods=["OPTIONS"])
async def kb_get_options(request: Request) -> Response:
    """Preflight for /api/notes/get."""
    return handle_options(request)


@mcp.custom_route("/api/notes/tags", methods=["GET"])
async def kb_tags(request: Request) -> Response:
    """Tag catalog frequency-sorted (-count, tag), case-normalized."""
    user = portal_auth.require_user(request)
    if user is None:
        return _deny_401(request)
    repo = get_note_repository()
    counts: dict[str, int] = {}
    display: dict[str, str] = {}
    for stem in repo.list_stems():
        try:
            note = repo.read_note(stem + ".md")
        except Exception:
            continue
        for raw_tag in list(note.metadata.tags or []):
            norm = raw_tag.strip().lower()
            if not norm:
                continue
            counts[norm] = counts.get(norm, 0) + 1
            display.setdefault(norm, raw_tag.strip())
    if not counts:
        return JSONResponse({"tags": [], "message": "No tags found."}, headers=_cors_headers(request))
    tags = [
        {"tag": display[k], "count": v}
        for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return JSONResponse(
        {"tags": tags, "message": f"Found {len(tags)} tag(s)."},
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/notes/tags", methods=["OPTIONS"])
async def kb_tags_options(request: Request) -> Response:
    """Preflight for /api/notes/tags."""
    return handle_options(request)


@mcp.custom_route("/api/notes/templates", methods=["GET"])
async def kb_templates(request: Request) -> Response:
    """Template catalog (name + skeleton + default tags) for the D-09 picker."""
    user = portal_auth.require_user(request)
    if user is None:
        return _deny_401(request)
    store = get_template_store()
    templates = []
    try:
        names = store.names()
    except Exception:
        names = []
    for name in names:
        try:
            spec = store.get(name)
        except Exception:
            continue
        if not isinstance(spec, dict):
            continue
        templates.append(
            {
                "name": name,
                "body_skeleton": spec.get("body_skeleton", ""),
                "default_tags": list(spec.get("default_tags", [])),
            }
        )
    return JSONResponse(
        {"templates": templates, "message": f"Found {len(templates)} template(s)."},
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/notes/templates", methods=["OPTIONS"])
async def kb_templates_options(request: Request) -> Response:
    """Preflight for /api/notes/templates."""
    return handle_options(request)


@mcp.custom_route("/api/notes/can_write", methods=["GET"])
async def kb_can_write(request: Request) -> Response:
    """D-14 disabled-controls probe: bool only, never token data."""
    user = portal_auth.require_user(request)
    if user is None:
        return _deny_401(request)
    return JSONResponse(
        {"can_write": bool(has_write_access(user.email))},
        headers=_cors_headers(request),
    )


@mcp.custom_route("/api/notes/can_write", methods=["OPTIONS"])
async def kb_can_write_options(request: Request) -> Response:
    """Preflight for /api/notes/can_write."""
    return handle_options(request)
