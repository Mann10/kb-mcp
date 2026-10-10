---
phase: 07-note-crud-operations
reviewed: 2026-10-10T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - src/kb_mcp/write_tools.py
  - src/kb_mcp/storage.py
  - src/kb_mcp/git_history.py
  - tests/test_write_tools.py
findings:
  critical: 1
  warning: 8
  info: 6
  total: 15
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-10-10T00:00:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the note CRUD path end-to-end at standard depth: `write_tools.py` (create/delete/update tool layer), `storage.py` (NoteRepository, atomic writes, rename), `git_history.py` (fail-open dulwich hooks), and `tests/test_write_tools.py` (reliability only), cross-referencing `validation.py`, `errors.py`, `middleware.py`, `models.py`, and `parsing.py` at call boundaries.

The core design is sound (slug gating, fail-open git, atomic-write intent, deterministic title fallback). However, the tool layer's contract — "structured dicts, never raised exceptions" — is broken on multiple reachable paths: storage exceptions (`FileIOError`, `MalformedYAMLError`, `MissingFieldError`, pydantic `ValidationError`) escape `create_note`, `delete_note`, and `update_note` uncaught. Additionally, `update_note` rejects whitespace-padded dates that `create_note` accepts, rename is not crash/rollback-safe, the create collision check is a racy check-then-act over an overwriting store, and broad `except Exception: continue` blocks silently hide failures. None of these require exotic input — a corrupt note file or a full disk is enough to trigger the critical path.

## Critical Issues

### CR-01: [BLOCKER] Storage exceptions escape tools as raised exceptions instead of structured returns

**File:** `src/kb_mcp/write_tools.py:130-133`, `src/kb_mcp/write_tools.py:151-154`, `src/kb_mcp/write_tools.py:216-229` (via `src/kb_mcp/storage.py:143`)
**Issue:** The tool contract is structured `{"success": False, ...}` dicts, but each tool catches only a subset of what the repository layer raises:
- `create_note` catches only `InvalidTypeError` around `repo.write_note()`. `write_note` raises `FileIOError` on any `_atomic_write` failure (disk full, permissions) and pydantic `ValidationError` (a `ValueError` subclass, not `InvalidTypeError`) from `NoteMetadata(...)` — both propagate to the caller as exceptions.
- `delete_note` catches only `NoteNotFoundError` around `repo.delete_note()`. An `unlink` failure raises `FileIOError`, which escapes.
- `update_note` calls `repo.update_note()` → `self.read_note()` → `parse_frontmatter()`, which raises `MalformedYAMLError` / `MissingFieldError` for corrupt notes (`parsing.py`). The tool catches only `(NoteNotFoundError, InvalidTypeError, ValueError, FileExistsError)` — `MalformedYAMLError` and `MissingFieldError` are not subclasses of any of those, so updating a note with corrupt frontmatter crashes the tool instead of returning a structured error. `FileIOError` from the rename path escapes the same way.
**Fix:**
```python
# create_note
try:
    note = repo.write_note(filename, display_title, body, list(normalized_tags), created)
except InvalidTypeError as e:
    return {"success": False, "message": f"Invalid note field: {e}."}
except Exception as e:  # FileIOError, ValidationError, OSError — storage is fallible
    return {"success": False, "message": f"Failed to create note '{display_title}': {e}."}
```
Apply the same catch-all-structured pattern to `delete_note` (around `repo.delete_note`) and `update_note` (around `repo.update_note` / `repo.read_note`, explicitly including `MalformedYAMLError`, `MissingFieldError`, `FileIOError`).

## Warnings

### WR-01: `update_note` rejects whitespace-padded `created` dates that `create_note` accepts

**File:** `src/kb_mcp/write_tools.py:194-200`, `src/kb_mcp/write_tools.py:222`
**Issue:** `create_note` normalizes with `datetime.date.fromisoformat(created.strip()).isoformat()` (line 115), so `" 2026-01-15 "` succeeds. `update_note` only *validates* with `datetime.date.fromisoformat(created.strip())` (line 198, result discarded) and then forwards the raw un-stripped `created` to `repo.update_note`, where `NoteMetadata` runs `datetime.date.fromisoformat(v)` without stripping — raising `ValidationError` and returning a spurious "Invalid note field" failure for input the create path accepts. Inconsistent validation across the two entry points for the same field.
**Fix:**
```python
if created is not None:
    if not isinstance(created, str):
        return {"success": False, "message": f"Invalid created: must be YYYY-MM-DD, got '{created}'."}
    try:
        created = datetime.date.fromisoformat(created.strip()).isoformat()
    except ValueError:
        return {"success": False, "message": f"Invalid created: must be YYYY-MM-DD, got '{created}'."}
```

### WR-02: Bare `except Exception: continue` in `_resolve_stem` hides I/O and validation failures

**File:** `src/kb_mcp/write_tools.py:79-84`
**Issue:** The display-title fallback loop catches every `Exception` from `repo.read_note()` — including `FileIOError`, `OSError`, and permission errors — and silently treats the note as non-matching. A transient I/O failure therefore resolves as "not found" instead of surfacing, and debugging is left with no log trail.
**Fix:**
```python
from .errors import InvalidTypeError, MalformedYAMLError, MissingFieldError, NoteNotFoundError
try:
    candidate = repo.read_note(stem + ".md")
except (NoteNotFoundError, MalformedYAMLError, MissingFieldError, InvalidTypeError, OSError):
    continue
```

### WR-03: `list_notes` silently drops unreadable notes with no log

**File:** `src/kb_mcp/storage.py:108-114`
**Issue:** Same anti-pattern as WR-02 at the repository layer: any per-file failure is swallowed and the note is skipped, so callers receive a silently incomplete list. A corrupt or unreadable note is indistinguishable from a nonexistent one.
**Fix:**
```python
import logging
logger = logging.getLogger(__name__)
try:
    content = file.read_text(encoding="utf-8-sig")
    metadata, _ = parse_frontmatter(content, file.name)
    notes.append(metadata)
except Exception as e:
    logger.warning("skipping unreadable note %s: %s: %s", file.name, type(e).__name__, e)
    continue
```

### WR-04: Create collision check is check-then-act over an overwriting store (TOCTOU, data loss on race)

**File:** `src/kb_mcp/write_tools.py:127-131`, `src/kb_mcp/storage.py:86-96`
**Issue:** `create_note` checks `(repo.notes_dir / filename).exists()` then calls `repo.write_note()`, which unconditionally overwrites (`existed = path.exists()` only changes the commit message to "update"). Two concurrent creates with the same title both pass the check; the second silently destroys the first note's body and the history records a misleading `note(update)`. The "never overwrites" (D-01) guarantee holds only in a single-threaded world.
**Fix:** Make the store the enforcer — add a `must_not_exist` / `overwrite=False` parameter to `write_note` that raises `FileExistsError` when the target exists, checked immediately before `_atomic_write`, and have `create_note` translate that into the existing structured exists-error (keeping the fast-path check for the good message).

### WR-05: Rename writes new file before deleting old with no rollback on failure

**File:** `src/kb_mcp/storage.py:168-182`
**Issue:** The rename path `_atomic_write(new_path)` → `old_path.unlink()` has two failure windows: a crash between the two leaves both files (duplicated note under two stems, title fallback becomes ambiguous); if `old_path.unlink()` raises, the `FileIOError` propagates while the new file remains — the caller is told the update failed, yet a half-completed rename persists with no cleanup.
**Fix:**
```python
try:
    old_path.unlink()
except Exception as e:
    try:
        new_path.unlink()  # roll back the half-rename
    except OSError:
        pass
    raise FileIOError(filename, "delete", str(e))
```

### WR-06: `_atomic_write` uses a fixed temp name and its cleanup can mask the original error

**File:** `src/kb_mcp/storage.py:26-34`
**Issue:** `temp_path = path.with_suffix(".tmp")` means concurrent writers to the same note share one temp file and can corrupt each other. Additionally, the `except` block calls `temp_path.unlink()` unguarded — if cleanup itself raises (permissions), it replaces the original write error. The bound `e` is also unused (bare `raise`).
**Fix:**
```python
import tempfile
fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.stem + ".", suffix=".tmp")
os.close(fd)
temp_path = Path(tmp)
try:
    temp_path.write_text(content, encoding="utf-8")
    os.replace(temp_path, path)
except Exception:
    try:
        if temp_path.exists():
            temp_path.unlink()
    except OSError:
        pass
    raise
```

### WR-07: Concurrent commits can co-mingle notes, violating one-file-per-commit (D-05)

**File:** `src/kb_mcp/git_history.py:55-78`, `src/kb_mcp/git_history.py:107-135`
**Issue:** The add → status → commit sequence is non-atomic across processes. Two simultaneous writers can each `porcelain.add` a different file before either commits, so one `porcelain.commit` sweeps both staged files into a single commit — breaking the D-05 invariant the module docstring claims. The single `FileLocked` retry mitigates lock contention, not staging interleaving.
**Fix:** Serialize the add/status/commit critical section with a filesystem lock (e.g., `filelock` around the notes dir, or dulwich's `FileLocked`-style lockfile held across all three steps), not just a one-shot add retry.

### WR-08: `.gitignore` existence check doesn't guarantee `*.tmp` is ignored

**File:** `src/kb_mcp/git_history.py:50-52`
**Issue:** `ensure_repo` writes `.gitignore` only when the file is absent. If a user (or tooling) replaces it without the `*.tmp` line, crash-residue atomic-write temp files become stageable and committable, defeating the guard the docstring describes.
**Fix:**
```python
gitignore = Path(repo_path) / ".gitignore"
existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
if "*.tmp" not in existing:
    with gitignore.open("a", encoding="utf-8") as f:
        f.write("*.tmp\n")
```

## Info

### IN-01: Redundant double `validate_path` calls

**File:** `src/kb_mcp/storage.py:82-84`, `src/kb_mcp/storage.py:117-119`
**Issue:** `write_note` and `delete_note` each call `validate_path(self.notes_dir, filename)` twice in succession, discarding the first result. Harmless but wasteful and suggests an editing leftover.
**Fix:** Keep one call: `path = validate_path(self.notes_dir, filename)` preceded by `validate_filename(filename)`.

### IN-02: Function-level imports indicate a circular-import workaround that should be documented or removed

**File:** `src/kb_mcp/storage.py:94`, `src/kb_mcp/storage.py:129`, `src/kb_mcp/storage.py:141`, `src/kb_mcp/storage.py:173`, `src/kb_mcp/storage.py:180`, `src/kb_mcp/storage.py:184`
**Issue:** `git_history` and `errors` imports are deferred into six function bodies. There is no actual cycle (`git_history` imports only stdlib/dulwich), so these can be top-level imports; as-is they add per-call overhead and inconsistency (`InvalidTypeError` imported mid-function while siblings are top-level).
**Fix:** Move `from .git_history import commit_note_file, commit_note_deletion, commit_note_rename` and `from .errors import InvalidTypeError, FileIOError` to module top.

### IN-03: Tags length check relies on `or` short-circuit ordering to avoid `TypeError`

**File:** `src/kb_mcp/write_tools.py:104-109`, `src/kb_mcp/write_tools.py:187-193`
**Issue:** `any(len(t) >= 100 for t in tags)` calls `len()` on elements assumed to be `str`; it is safe today only because the preceding `any(not isinstance(t, str) ...)` clause short-circuits the `or` chain first. A reorder during refactoring introduces a `TypeError` crash on input like `[123]`.
**Fix:** Make each check self-guard: `any(not isinstance(t, str) or len(t) >= 100 for t in tags)`.

### IN-04: Git staged-check couples to a specific dulwich `status()` result shape

**File:** `src/kb_mcp/git_history.py:68-69`, `src/kb_mcp/git_history.py:94-95`, `src/kb_mcp/git_history.py:125-126`
**Issue:** `porcelain.status(repo_arg).staged["add" | "delete" | "modify"]` assumes a dict-shaped staged result. A dulwich upgrade changing this API turns every commit into a silent no-commit (swallowed by the fail-open handler) with only a warning log.
**Fix:** Pin the dulwich version range in dependencies and/or access defensively, e.g. `getattr(staged, "get", lambda k: getattr(staged, k, None))`, plus a test asserting a commit is produced (as `test_update_rename_single_commit` does) run against the pinned version.

### IN-05: Inconsistent `created` error wording between create and update

**File:** `src/kb_mcp/write_tools.py:113`, `src/kb_mcp/write_tools.py:196`
**Issue:** Create reports `"Invalid created: must be an ISO date (YYYY-MM-DD), got ..."` while update reports `"Invalid created: must be YYYY-MM-DD, got ..."`. Clients matching on message text see two formats for one field.
**Fix:** Use one shared constant for the message in both functions.

### IN-06: `list_notes` sort has no secondary key — same-date order is OS-dependent

**File:** `src/kb_mcp/storage.py:114`
**Issue:** `sorted(notes, key=lambda n: n.created)` leaves same-`created` notes in `iterdir()` order, which is filesystem-dependent and nondeterministic across machines.
**Fix:** `return sorted(notes, key=lambda n: (n.created, n.title))` or include filename once available on the metadata.

---

_Reviewed: 2026-10-10T00:00:00Z_
_Reviewer: OpenCode (gsd-code-reviewer)_
_Depth: standard_
