---
phase: 08-tag-management-templates
reviewed: 2026-10-10T06:46:53Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - src/kb_mcp/write_tools.py
  - tests/test_tag_tools.py
  - tests/test_templates.py
findings:
  critical: 0
  warning: 6
  info: 7
  total: 13
status: issues_found
---

# Phase 08: Code Review Report

**Reviewed:** 2026-10-10T06:46:53Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Reviewed `src/kb_mcp/write_tools.py` (443 lines — `add_tags`, `remove_tags`,
`create_from_template`, plus pre-existing `create_note`/`update_note`/`delete_note`
in the same module) with cross-references into `storage.py`, `models.py`,
`validation.py`, `middleware.py`, and `errors.py`, plus both test files for
reliability issues only.

**Security posture is sound:** all five mutating entry points carry
`@require_write` (verified by auth-denied tests); user input never reaches the
filesystem unsanitized — filenames are derived exclusively via `_slugify_title`
(`[a-z0-9_-]` charset) plus `validate_filename`/`validate_path` defense-in-depth
in `NoteRepository`, and `_resolve_stem` never builds paths from raw input.
Pattern scan for `eval`/`exec`/hardcoded secrets came back clean (only
`secrets`-stdlib usage in out-of-scope `auth.py` and docstring mentions in
`cli.py`). No BLOCKER-grade issue was provable.

**Correctness, however, has real gaps:** tag validation is enforced
inconsistently across sibling functions (blank tags accepted in two paths,
rejected in three), tags/created values are stored un-normalized in some paths
but normalized in others, and every tool's `except` clauses are too narrow — a
vault containing one externally-created or corrupt note (uppercase/space in
filename, malformed frontmatter) turns `add_tags`/`remove_tags`/`update_note`/
`delete_note` into unhandled tracebacks instead of the structured payloads the
module promises. Findings below are ordered by severity.

## Warnings

### WR-01: [WARNING] Blank/whitespace-only tags accepted by create/update but rejected by add/remove/template

**File:** `src/kb_mcp/write_tools.py:103-109`, `187-193` vs `243-254`, `393-395`
**Issue:** `create_note` and `update_note` validate tags with an inline check
(`isinstance str`, `len < 100`) that does **not** reject `""` or `"   "`.
`_validate_tag_list` (used by `add_tags`/`remove_tags`) *does* reject blanks
(lines 251-253), and `create_from_template` rejects them twice (lines 393-395,
409-411). `NoteMetadata.tags_must_be_valid_strings` (`models.py:26-35`) also
permits blanks, so `create_note("X", tags=["   "])` persists a whitespace-only
tag that sibling APIs would refuse — junk data the rest of the system never
anticipated (search/filter/display on a blank tag is undefined).
**Fix:** Delete the three inline copies and route every path through the one
helper:
```python
# create_note / update_note / create_from_template, replacing inline checks:
invalid = _validate_tag_list(tags)
if invalid is not None:
    return {"success": False, "message": invalid}
```

### WR-02: [WARNING] Tags stored un-stripped by create/update while tag ops normalize

**File:** `src/kb_mcp/write_tools.py:131`, `221`
**Issue:** `create_note` passes `list(normalized_tags)` and `update_note`
passes `list(tags)` to the repo verbatim, preserving leading/trailing
whitespace (`tags=["  work "]` is stored as `"  work "`). But `add_tags`
strips incoming tags (line 264) and `remove_tags` compares stripped/lowered
(line 322), so the vault accumulates display variants (`"  work "` vs
`"work"`) that compare equal in one code path and unequal in another. Listing
output then shows padded tags the tag-ops API claims don't exist in that form.
**Fix:**
```python
# create_note line 131 and update_note line 221:
note = repo.write_note(filename, display_title, body,
                       [t.strip() for t in normalized_tags], created)
tags=( [t.strip() for t in tags] if tags is not None else None),
```
(combined with WR-01, blanks are rejected before stripping ever matters).

### WR-03: [WARNING] `update_note` passes `created` through raw — no normalization, divergent from create

**File:** `src/kb_mcp/write_tools.py:194-200`, `222`
**Issue:** `create_note` (line 115) and `create_from_template` (line 417)
re-assign `created = date.fromisoformat(...).isoformat()`, so `"2026-1-5"`
is stored canonically as `"2026-01-05"`. `update_note` validates with
`fromisoformat(created.strip())` but passes the **raw** string to
`repo.update_note`, persisting non-canonical `"2026-1-5"`. Same field, two
canonical forms depending on which tool wrote it — sorting/display/comparison
consumers see inconsistent data.
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

### WR-04: [WARNING] Narrow `except` clauses turn corrupt/foreign notes into unhandled tracebacks

**File:** `src/kb_mcp/write_tools.py:130-133`, `151-154`, `175-178`, `216-229`, `268-294`, `316-337`, `432-435`
**Issue:** Every tool catches only `NoteNotFoundError` (plus
`InvalidTypeError`/`ValueError` on some paths) around `repo.read_note` /
`repo.update_note` / `repo.write_note` / `repo.delete_note`. Those repo calls
can also raise `MalformedYAMLError`, `MissingFieldError`, `FileIOError`
(disk/permission/git-commit failure), and `InvalidTypeError` from
`validate_filename`. Two concrete, provable triggers:
1. A manually placed `My Note.md` (uppercase/space — `_resolve_stem` happily
   resolves it via directory listing) makes `repo.read_note("My Note.md")`
   raise `InvalidTypeError`, which `add_tags`/`remove_tags`/`update_note`/
   `delete_note` do **not** catch → traceback instead of a structured payload.
2. A note with corrupt frontmatter makes `add_tags` raise
   `MalformedYAMLError` uncaught for the same reason.
3. `FileIOError` from `_atomic_write` (storage.py:92) or a failing git commit
   is uncaught on **all** write paths (`create_note` line 132 catches only
   `InvalidTypeError`, missing even the `ValueError` its siblings catch).
**Fix:** Widen to the repo's documented failure surface and return structured
errors:
```python
from .errors import FileIOError, InvalidTypeError, MalformedYAMLError, MissingFieldError, NoteNotFoundError
try:
    note = repo.read_note(real_stem + ".md")
except NoteNotFoundError:
    return {"success": False, "message": f"Note '{title}' not found."}
except (MalformedYAMLError, MissingFieldError, InvalidTypeError, FileIOError, OSError) as e:
    return {"success": False, "message": f"Note '{title}' is unreadable: {e}."}
```
Apply symmetrically to the `write_note`/`update_note`/`delete_note` call sites
(catching `FileIOError`/`OSError` → `{"success": False, ...}`).

### WR-05: [WARNING] `_resolve_stem` silently swallows I/O and corruption signals

**File:** `src/kb_mcp/write_tools.py:66-73`, `78-85`
**Issue:** `except OSError: stem_map = {}` (line 72) converts an unreadable
notes directory into a fake empty vault — every caller then reports "not
found" instead of an error, misdirecting debugging. `except Exception:
continue` (line 81) in the display-title fallback silently skips
malformed/unreadable notes, so title resolution can fail with "not found" when
the note exists but is corrupt, hiding vault damage from the operator.
**Fix:** Let directory-level `OSError` propagate to the WR-04 structured-error
handling, and narrow the per-note skip to expected parse failures:
```python
from .errors import MalformedYAMLError, MissingFieldError, InvalidTypeError
try:
    candidate = repo.read_note(stem + ".md")
except (NoteNotFoundError, MalformedYAMLError, MissingFieldError, InvalidTypeError):
    continue
```

### WR-06: [WARNING] Rename collision pre-check false-positives on case-insensitive filesystems

**File:** `src/kb_mcp/write_tools.py:211-215`
**Issue:** The guard compares the lowercased `slug` against the verbatim
`real_stem` case-sensitively, then probes `(notes_dir / (slug + ".md")).exists()`.
For an externally created `My-Note.md`, `real_stem` is `"My-Note"` while any
rename slug is lowercase; on Windows/macOS (case-insensitive FS — this repo
runs on Windows) the `exists()` probe matches the note's *own* file and the
rename is wrongly rejected as "already exists". (`storage.update_note` has the
same shape at `storage.py:161-166`, but the tool-layer message fires first.)
**Fix:** Compare case-insensitively and exempt the note's own file:
```python
if slug is not None and slug.lower() != real_stem.lower() and (repo.notes_dir / (slug + ".md")).exists():
    # still need same-file exemption on case-insensitive FS:
    if (repo.notes_dir / (slug + ".md")).resolve() != (repo.notes_dir / (real_stem + ".md")).resolve():
        return {"success": False, "message": ...}
```

## Info

### IN-01: [WARNING] Hardcoded template list in unknown-template error goes stale

**File:** `src/kb_mcp/write_tools.py:379`
**Issue:** `f"Unknown template '{template}'. Valid templates: book, idea, meeting."`
hardcodes the keys of `TEMPLATES`. Adding a fourth template requires editing
the message in lockstep; the test (`test_templates.py:83-85`) already asserts
each name appears, so drift breaks tests too.
**Fix:**
```python
valid = ", ".join(sorted(TEMPLATES))
return {"success": False, "message": f"Unknown template '{template}'. Valid templates: {valid}."}
```

### IN-02: [WARNING] f-strings without placeholders ignore the computed `invalid` message

**File:** `src/kb_mcp/write_tools.py:263`, `311`
**Issue:** Both lines build `f"Invalid tags: ..."` with no placeholders instead
of returning the already-computed `invalid` variable (which holds
`INVALID_TAGS_MESSAGE`). A future edit to the constant silently diverges from
these two call sites; linters flag `f-string without any placeholders`.
**Fix:** `return {"success": False, "message": invalid}` on both lines.

### IN-03: Info — Magic number `100` (max tag length) repeated six times

**File:** `src/kb_mcp/write_tools.py:107`, `191`, `248`, `390`, `406` (+ `models.py:33`)
**Issue:** The 100-char tag limit is copy-pasted across every validator. A
policy change means touching six lines in two files and risking divergence
(which already happened with the blank-tag rule, WR-01).
**Fix:** `MAX_TAG_LENGTH = 100` in `models.py` (or `validation.py`), imported
wherever `len(t) >= MAX_TAG_LENGTH` is checked.

### IN-04: Info — Duplicated slugify and date-parse blocks across module (and `storage.py`)

**File:** `src/kb_mcp/write_tools.py:40-49`, `110-117`, `194-200`, `412-419`
**Issue:** `_slugify_title` re-implements `storage._slugify_stem` plus `".md"`,
and the `fromisoformat(...).isoformat()` created-date dance is triplicated.
Three copies already drifted (WR-03 proves it).
**Fix:** Single `_parse_created(value) -> str | None` helper in `write_tools.py`;
have `_slugify_title` delegate to `storage._slugify_stem` (or move one copy to
`validation.py`).

### IN-05: Info — Unused `middleware` message re-exports

**File:** `src/kb_mcp/write_tools.py:16-20`
**Issue:** `INVALID_TOKEN_MESSAGE` / `WRITE_DENIED_MESSAGE` are imported "for
tests" (`noqa: F401`), but both test files import them directly from
`kb_mcp.middleware` (`test_tag_tools.py:7`, `test_templates.py:9`) — the
re-export has no consumers.
**Fix:** Remove the re-export import; keep the `require_write` import only.

### IN-06: Info — `filename` field carries the stem, not a filename

**File:** `src/kb_mcp/write_tools.py:136`, `155`, `181`, `230`, `296`, `340`, `437`
**Issue:** Every success payload's `"filename"` holds `note.filename`, which
`storage.py:99` sets to `path.stem` — i.e. `"tag-target"`, no `.md` (tests
enshrine this, e.g. `test_tag_tools.py:29`). Consumers treating it as a literal
filename for filesystem use get a path that doesn't exist. Not asking for a
contract break — just naming drift worth documenting.
**Fix:** Document in each docstring that `filename` is the extensionless stem,
or add an explicit `"stem"` alias. No behavior change without a versioned
contract update.

### IN-07: Info — Midnight-boundary flake in date assertions (test reliability)

**File:** `tests/test_templates.py:24-33`, `36-45`, `48-57`, `142-151`
**Issue:** `out["created"] == datetime.date.today().isoformat()` fails if the
suite runs across a UTC-date rollover between tool call and assertion
(`create_from_template` stamps `date.today()` internally). Same shape as the
production/test clock-skew class, low probability but a real flake.
**Fix:** Capture `before = date.today()` prior to the call and assert
`out["created"] in {before.isoformat(), date.today().isoformat()}`, or
freeze time with `freezegun`/`unittest.mock`.

---

_Reviewed: 2026-10-10T06:46:53Z_
_Reviewer: OpenCode (gsd-code-reviewer)_
_Depth: standard_
