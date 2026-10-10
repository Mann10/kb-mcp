"""Create + delete write tools with structured returns (WRITE-01, WRITE-04).

Lineage: D-01 (create rejects existing, never overwrites), D-02 (created
defaults to today ISO), D-03 (slug filename, display title in frontmatter),
D-04 (structured validation payloads), D-13 (delete missing is structured
not-found), D-14 (immediate exec, git commit is the safety net), D-15
(require_write gating), D-16 (success payloads carry full fields + message).

All filesystem I/O goes through NoteRepository — never direct writes.
"""

import datetime
import re

from .errors import InvalidTypeError, NoteNotFoundError
from .middleware import (
    INVALID_TOKEN_MESSAGE,  # noqa: F401  (re-exported for tests)
    WRITE_DENIED_MESSAGE,  # noqa: F401  (re-exported for tests)
    require_write,
)
from .storage import NoteRepository
from .validation import validate_filename

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


def _resolve_stem(repo: NoteRepository, name: str) -> str | None:
    """Resolve a user-supplied name to a canonical stem (D-07 mirror).

    Case-insensitive stem match first, then display-title fallback over
    stems sorted for determinism. Returns None when unresolvable.
    """
    if not isinstance(name, str):
        return None
    wanted_raw = name.strip()
    if wanted_raw.lower().endswith(".md"):
        wanted_raw = wanted_raw[:-3]
    wanted = wanted_raw.strip()
    if not wanted:
        return None
    try:
        stem_map = {
            p.stem.lower(): p.stem
            for p in repo.notes_dir.iterdir()
            if p.is_file() and p.suffix == ".md"
        }
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


@require_write
def create_note(
    title: str,
    body: str = "",
    tags: list[str] | None = None,
    created: str | None = None,
    *,
    token=None,
    _store=None,
) -> dict:
    """Create a new note; reject collisions with a structured exists-error."""
    repo = _resolve_repo()
    if not isinstance(title, str) or not title.strip():
        return {"success": False, "message": "Invalid title: must be a non-empty string."}
    display_title = title.strip()
    normalized_tags = [] if tags is None else tags
    if (
        not isinstance(normalized_tags, list)
        or any(not isinstance(t, str) for t in normalized_tags)
        or any(len(t) >= 100 for t in normalized_tags)
    ):
        return {"success": False, "message": "Invalid tags: must be a list of strings each under 100 characters."}
    if created is None:
        created = datetime.date.today().isoformat()
    if not isinstance(created, str):
        return {"success": False, "message": f"Invalid created: must be an ISO date (YYYY-MM-DD), got '{created}'."}
    try:
        created = datetime.date.fromisoformat(created.strip()).isoformat()
    except ValueError:
        return {"success": False, "message": f"Invalid created: must be an ISO date (YYYY-MM-DD), got '{created}'."}
    if not isinstance(body, str):
        return {"success": False, "message": "Invalid body: must be a string."}
    filename = _slugify_title(display_title)
    if filename is None:
        return {"success": False, "message": "Invalid title: must slugify to a safe filename."}
    try:
        validate_filename(filename)
    except InvalidTypeError:
        return {"success": False, "message": "Invalid title: must slugify to a safe filename."}
    if (repo.notes_dir / filename).exists():
        stem = filename[:-3]
        return {"success": False, "message": f"Note '{display_title}' already exists as {stem}."}
    try:
        note = repo.write_note(filename, display_title, body, list(normalized_tags), created)
    except InvalidTypeError as e:
        return {"success": False, "message": f"Invalid note field: {e}."}
    return {
        "success": True,
        "filename": note.filename,
        "title": note.metadata.title,
        "tags": list(note.metadata.tags),
        "created": note.metadata.created,
        "message": f"Note '{note.metadata.title}' created as {note.filename}.",
    }


@require_write
def delete_note(title: str, *, token=None, _store=None) -> dict:
    """Delete a note by title/stem; missing notes are structured not-found."""
    repo = _resolve_repo()
    stem = _resolve_stem(repo, title) if isinstance(title, str) else None
    if stem is None:
        return {"success": False, "message": f"Note '{title}' not found."}
    try:
        repo.delete_note(stem + ".md")
    except NoteNotFoundError:
        return {"success": False, "message": f"Note '{title}' not found."}
    return {"success": True, "filename": stem, "message": f"Note '{stem}' deleted."}


@require_write
def update_note(
    title: str,
    new_title: str | None = None,
    body: str | None = None,
    tags: list[str] | None = None,
    created: str | None = None,
    *,
    token=None,
    _store=None,
) -> dict:
    """Update content/metadata of an existing note; rename on new_title."""
    repo = _resolve_repo()
    if new_title is None and body is None and tags is None and created is None:
        real_stem = _resolve_stem(repo, title) if isinstance(title, str) else None
        if real_stem is None:
            return {"success": False, "message": f"Note '{title}' not found."}
        try:
            note = repo.read_note(real_stem + ".md")
        except NoteNotFoundError:
            return {"success": False, "message": f"Note '{title}' not found."}
        return {
            "success": True,
            "filename": note.filename,
            "title": note.metadata.title,
            "tags": list(note.metadata.tags),
            "created": note.metadata.created,
            "message": f"No changes — note '{title}' unchanged.",
        }
    if tags is not None:
        if (
            not isinstance(tags, list)
            or any(not isinstance(t, str) for t in tags)
            or any(len(t) >= 100 for t in tags)
        ):
            return {"success": False, "message": "Invalid tags: must be a list of strings each under 100 characters."}
    if created is not None:
        if not isinstance(created, str):
            return {"success": False, "message": f"Invalid created: must be YYYY-MM-DD, got '{created}'."}
        try:
            datetime.date.fromisoformat(created.strip())
        except ValueError:
            return {"success": False, "message": f"Invalid created: must be YYYY-MM-DD, got '{created}'."}
    if new_title is not None:
        if not isinstance(new_title, str) or not new_title.strip():
            return {"success": False, "message": "Invalid title: must be a non-empty string."}
        if _slugify_title(new_title) is None:
            return {"success": False, "message": f"Invalid title: '{new_title}' cannot form a safe filename."}
    if body is not None and not isinstance(body, str):
        return {"success": False, "message": "Invalid body: must be a string."}
    real_stem = _resolve_stem(repo, title) if isinstance(title, str) else None
    if real_stem is None:
        return {"success": False, "message": f"Note '{title}' not found."}
    if new_title is not None:
        slug_file = _slugify_title(new_title)
        slug = slug_file[:-3] if slug_file is not None else None
        if slug is not None and slug != real_stem and (repo.notes_dir / (slug + ".md")).exists():
            return {"success": False, "message": f"Note '{new_title.strip()}' already exists as '{slug}'. Rename rejected."}
    try:
        note = repo.update_note(
            real_stem + ".md",
            title=(new_title.strip() if new_title is not None else None),
            body=body,
            tags=(list(tags) if tags is not None else None),
            created=created,
        )
    except NoteNotFoundError:
        return {"success": False, "message": f"Note '{title}' not found."}
    except (InvalidTypeError, ValueError) as e:
        return {"success": False, "message": f"Invalid note field: {e}."}
    except FileExistsError as e:
        return {"success": False, "message": f"Note '{new_title}' already exists. Rename rejected. ({e})"}
    return {
        "success": True,
        "filename": note.filename,
        "title": note.metadata.title,
        "tags": list(note.metadata.tags),
        "created": note.metadata.created,
        "message": f"Updated note '{note.metadata.title}'.",
    }


INVALID_TAGS_MESSAGE = "Invalid tags: must be a list of strings each under 100 characters."


def _validate_tag_list(tags) -> str | None:
    """Return None when valid, else the structured invalid-tags message."""
    if (
        not isinstance(tags, list)
        or any(not isinstance(t, str) for t in tags)
        or any(len(t) >= 100 for t in tags)
    ):
        return INVALID_TAGS_MESSAGE
    for t in tags:
        if not t.strip():
            return INVALID_TAGS_MESSAGE
    return None


@require_write
def add_tags(title: str, tags: list[str], *, token=None, _store=None) -> dict:
    """Add tags to an existing note; duplicates are idempotent success (D-02/D-05/D-06)."""
    repo = _resolve_repo()
    invalid = _validate_tag_list(tags)
    if invalid is not None:
        return {"success": False, "message": f"Invalid tags: must be a list of strings each under 100 characters."}
    incoming = [t.strip() for t in tags]
    real_stem = _resolve_stem(repo, title) if isinstance(title, str) else None
    if real_stem is None:
        return {"success": False, "message": f"Note '{title}' not found."}
    try:
        note = repo.read_note(real_stem + ".md")
    except NoteNotFoundError:
        return {"success": False, "message": f"Note '{title}' not found."}
    existing = list(note.metadata.tags or [])
    seen = {t.strip().lower() for t in existing}
    merged = list(existing)
    for s in incoming:
        if s.lower() in seen:
            continue
        merged.append(s)
        seen.add(s.lower())
    if merged == existing:
        return {
            "success": True,
            "filename": note.filename,
            "title": note.metadata.title,
            "tags": list(note.metadata.tags),
            "created": note.metadata.created,
            "message": f"No changes — note '{note.metadata.title}' already has those tags.",
        }
    try:
        updated = repo.update_note(real_stem + ".md", tags=merged)
    except NoteNotFoundError:
        return {"success": False, "message": f"Note '{title}' not found."}
    except (InvalidTypeError, ValueError) as e:
        return {"success": False, "message": f"Invalid note field: {e}."}
    return {
        "success": True,
        "filename": updated.filename,
        "title": updated.metadata.title,
        "tags": list(updated.metadata.tags),
        "created": updated.metadata.created,
        "message": f"Added {len(merged) - len(existing)} tag(s) to '{updated.metadata.title}'.",
    }


@require_write
def remove_tags(title: str, tags: list[str], *, token=None, _store=None) -> dict:
    """Remove tags from an existing note; missing tags are idempotent success (D-03/D-08)."""
    repo = _resolve_repo()
    invalid = _validate_tag_list(tags)
    if invalid is not None:
        return {"success": False, "message": f"Invalid tags: must be a list of strings each under 100 characters."}
    incoming = [t.strip() for t in tags]
    real_stem = _resolve_stem(repo, title) if isinstance(title, str) else None
    if real_stem is None:
        return {"success": False, "message": f"Note '{title}' not found."}
    try:
        note = repo.read_note(real_stem + ".md")
    except NoteNotFoundError:
        return {"success": False, "message": f"Note '{title}' not found."}
    existing = list(note.metadata.tags or [])
    drop = {s.lower() for s in incoming}
    kept = [t for t in existing if t.strip().lower() not in drop]
    if kept == existing:
        return {
            "success": True,
            "filename": note.filename,
            "title": note.metadata.title,
            "tags": list(note.metadata.tags),
            "created": note.metadata.created,
            "message": f"No changes — note '{note.metadata.title}' already lacks those tags.",
        }
    try:
        updated = repo.update_note(real_stem + ".md", tags=kept)
    except NoteNotFoundError:
        return {"success": False, "message": f"Note '{title}' not found."}
    except (InvalidTypeError, ValueError) as e:
        return {"success": False, "message": f"Invalid note field: {e}."}
    return {
        "success": True,
        "filename": updated.filename,
        "title": updated.metadata.title,
        "tags": list(updated.metadata.tags),
        "created": updated.metadata.created,
        "message": f"Removed {len(existing) - len(kept)} tag(s) from '{updated.metadata.title}'.",
    }
