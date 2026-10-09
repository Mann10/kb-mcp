"""Keyword search and single-note retrieval tools (READ-01, READ-02).

Both tools are gated behind ``require_read`` and return structured dicts
for AI clients to parse. Expected empty states (no matches, missing note)
return structured payloads with a human-readable ``message`` field — never
bare strings and never raised errors.
"""

from .errors import NoteNotFoundError
from .middleware import require_read
from .parsing import parse_frontmatter  # noqa: F401  (re-exported contract import)
from .storage import NoteRepository

DEFAULT_LIMIT = 10
MAX_LIMIT = 50
SNIPPET_CONTEXT = 120

_default_repo: NoteRepository | None = None


def configure_default_repo(repo: NoteRepository | None) -> None:
    """Set the module-level default repo used when test injection is needed."""
    global _default_repo
    _default_repo = repo


def _resolve_repo() -> NoteRepository:
    """Return the injected repo, or a default ``NoteRepository()``."""
    if _default_repo is not None:
        return _default_repo
    return NoteRepository()


def _build_snippet(body: str, q: str, hit_index: int) -> str:
    """Keyword-in-context snippet around the first body match."""
    start = max(0, hit_index - SNIPPET_CONTEXT)
    end = min(len(body), hit_index + len(q) + SNIPPET_CONTEXT)
    snippet = " ".join(body[start:end].split())
    if start > 0:
        snippet = "\u2026" + snippet
    if end < len(body):
        snippet = snippet + "\u2026"
    return snippet


@require_read
def search_notes(query: str, limit: int = 10, *, token=None, _store=None) -> dict:
    """Search notes by keyword across body + title + stem + tags."""
    repo = _resolve_repo()
    if not isinstance(limit, int) or limit <= 0:
        limit = DEFAULT_LIMIT
    else:
        limit = min(limit, MAX_LIMIT)
    if not isinstance(query, str) or not query.strip():
        return {"results": [], "message": f"No notes found matching '{query}'."}
    q = query.strip().lower()
    try:
        stems = sorted(
            p.stem
            for p in repo.notes_dir.iterdir()
            if p.is_file() and p.suffix == ".md"
        )
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
        hit_index = body.lower().find(q)
        body_hit = hit_index >= 0
        title_hit = q in title.lower() or q in stem.lower()
        tags_hit = any(q in t.lower() for t in tags)
        if not (body_hit or title_hit or tags_hit):
            continue
        if body_hit:
            rank = 0
            snippet = _build_snippet(body, q, hit_index)
        elif title_hit:
            rank = 1
            snippet = " ".join(body[:200].split())
        else:
            rank = 2
            snippet = " ".join(body[:200].split())
        ranked.append(
            (
                rank,
                note.metadata.created,
                {
                    "filename": stem,
                    "title": title,
                    "tags": tags,
                    "created": note.metadata.created,
                    "snippet": snippet,
                },
            )
        )
    ranked.sort(key=lambda item: (item[0], item[1]))
    results = [payload for _, _, payload in ranked[:limit]]
    if not results:
        return {"results": [], "message": f"No notes found matching '{query}'."}
    count = len(results)
    return {
        "results": results,
        "message": f"Found {count} note(s) matching '{query}'.",
    }


@require_read
def get_note(title: str, *, token=None, _store=None) -> dict:
    """Retrieve a single note by case-insensitive title/stem lookup."""
    repo = _resolve_repo()
    name = (title or "").strip()
    if name.lower().endswith(".md"):
        name = name[:-3]
    if not name:
        return {"found": False, "message": f"Note '{title}' not found."}
    try:
        stem_map = {
            p.stem.lower(): p.stem
            for p in repo.notes_dir.iterdir()
            if p.is_file() and p.suffix == ".md"
        }
    except OSError:
        stem_map = {}
    real_stem = stem_map.get(name.lower())
    if real_stem is None:
        return {"found": False, "message": f"Note '{title}' not found."}
    try:
        note = repo.read_note(real_stem + ".md")
    except NoteNotFoundError:
        return {"found": False, "message": f"Note '{title}' not found."}
    except Exception:
        return {"found": False, "message": f"Note '{title}' not found."}
    return {
        "found": True,
        "filename": note.filename,
        "title": note.metadata.title,
        "tags": list(note.metadata.tags),
        "created": note.metadata.created,
        "body": note.body,
    }
