---
phase: 05-core-read-tools
reviewed: 2026-10-09T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - src/kb_mcp/read_tools.py
  - tests/test_read_tools.py
findings:
  critical: 1
  warning: 4
  info: 4
  total: 9
status: issues
---

# Phase 05: Code Review Report

**Reviewed:** 2026-10-09T00:00:00Z
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues

## Summary

Reviewed `src/kb_mcp/read_tools.py` (216 lines, 4 gated tools: `search_notes`, `list_notes`, `get_tags`, `get_note`) and `tests/test_read_tools.py` (213 lines) at standard depth, cross-referencing `storage.py`, `parsing.py`, `middleware.py`, `models.py`, `errors.py`, and `validation.py`. Auth gating is correct on all four tools and path-traversal handling is safe (stem-map indirection, no user input reaches the filesystem directly). The headline defect is that `get_note` documents case-insensitive title/stem lookup but implements stem-only lookup, so title queries always miss. Additional warnings cover a crash on non-string titles, silent/broad exception swallowing with misleading miss messages, per-file error isolation gaps, and bool/float `limit` coercion. Info items cover stale docs, duplication, and weak tests that let the title bug go undetected.

## Critical Issues

### CR-01: get_note promises title lookup but only matches filename stems

**File:** `src/kb_mcp/read_tools.py:183-202`
**Issue:** Docstring (line 185) states "Retrieve a single note by case-insensitive title/stem lookup", but the implementation builds `stem_map` from `p.stem` only (lines 193-197) and looks up `stem_map.get(name.lower())` (line 200). A query by display title (e.g. `get_note("Alpha Note")` for file `alpha-note.md` with title `"Alpha Note"`) never matches and returns `{"found": False}`. No test exercises title-based lookup — all `get_*` tests pass stems (`alpha-note`, `ALPHA-NOTE`, `beta-note.md`), so the gap is undetected. Either the contract or the code is wrong; callers relying on the documented title path get false misses. **BLOCKER.**
**Fix:**
```python
# Build both a stem map and a title map, then try stem first, title second.
stem_map = {
    p.stem.lower(): p.stem
    for p in repo.notes_dir.iterdir()
    if p.is_file() and p.suffix == ".md"
}
real_stem = stem_map.get(name.lower())
if real_stem is None:
    # Fall back to scanning display titles (skip unreadable files).
    for stem in sorted(stem_map.values()):
        try:
            candidate = repo.read_note(stem + ".md")
        except Exception:
            continue
        if (candidate.metadata.title or "").strip().lower() == name.lower():
            real_stem = stem
            break
if real_stem is None:
    return {"found": False, "message": f"Note '{title}' not found."}
```
Alternatively, correct the docstring to "stem-only lookup" if title search is out of scope — but then it is a contract change, not a silent doc lie.

## Warnings

### WR-01: get_note crashes on non-string title instead of returning structured miss

**File:** `src/kb_mcp/read_tools.py:187`
**Issue:** `name = (title or "").strip()` assumes `title` is `str` or `None`. A non-string truthy value (e.g. `get_note(123)`, `get_note(["x"])` — plausible from a loose JSON/MCP caller) raises `AttributeError: 'int' object has no attribute 'strip'`, which escapes the tool instead of returning the documented `{"found": False, ...}` payload the module docstring promises ("never raised errors" for expected empty states). `search_notes` (line 54) already guards with `not isinstance(query, str)`, so the two tools are inconsistent. **WARNING.**
**Fix:**
```python
if not isinstance(title, str):
    return {"found": False, "message": f"Note '{title}' not found."}
name = title.strip()
```

### WR-02: Overly broad `except Exception` silently swallows corruption and misreports it

**File:** `src/kb_mcp/read_tools.py:67-70, 127-131, 163-167, 203-208`
**Issue:** Every tool catches bare `except Exception: continue` (or maps everything to "not found" in `get_note`, lines 205-208) with no logging. Consequences: (a) a file that exists but is corrupt (e.g. `bad-note.md`) is reported by `get_note("bad-note")` as "not found" rather than surfaced as corrupt — misleading; (b) genuine programming errors (e.g. `AttributeError` from a schema change) are hidden, making future refactors fail silently; (c) operators get zero observability into KB rot. The skip-corrupt-file policy is reasonable for `search_notes`/`list_notes`/`get_tags`, but it must be narrowed and logged. **WARNING.**
**Fix:**
```python
import logging
logger = logging.getLogger(__name__)
# ...
from .errors import MalformedYAMLError, MissingFieldError, InvalidTypeError
from pydantic import ValidationError
_SKIP_ERRORS = (MalformedYAMLError, MissingFieldError, InvalidTypeError, ValidationError, OSError, UnicodeDecodeError)
try:
    note = repo.read_note(stem + ".md")
except _SKIP_ERRORS as e:
    logger.warning("skipping unreadable note %s: %s", stem, e)
    continue
```
And in `get_note`, distinguish corrupt from missing (different message or a `corrupt: True` flag) instead of returning identical "not found" for both.

### WR-03: Tag/metadata aggregation runs outside the per-file guard — one bad note can crash the whole call

**File:** `src/kb_mcp/read_tools.py:168-173` (also `src/kb_mcp/read_tools.py:132-134, 136-144`)
**Issue:** In `get_tags`, the `try` covers only `read_text` + `parse_frontmatter` (lines 163-167); the tag-normalization loop (`raw.strip().lower()`, lines 168-173) runs unguarded. A single note whose `tags` payload contains a non-string entry (which `parse_frontmatter` is supposed to reject, but defense-in-depth matters given WR-02's broad catching elsewhere) raises `AttributeError` and aborts the entire aggregation instead of skipping that file. Same shape in `list_notes`: `pairs.append` (line 132) and the `list(m.tags)` comprehension (line 140) plus `pairs.sort` (line 133) execute outside any guard. Per-file work must be per-file guarded. **WARNING.**
**Fix:**
```python
for path in sorted(files, key=lambda p: p.name):
    try:
        content = path.read_text(encoding="utf-8-sig")
        metadata, _ = parse_frontmatter(content, path.name)
        file_tags = list(metadata.tags or [])
    except Exception:
        continue
    for raw in file_tags:
        if not isinstance(raw, str):
            continue
        norm = raw.strip().lower()
        ...
```

### WR-04: `limit` type check accepts `bool` and silently rewrites floats

**File:** `src/kb_mcp/read_tools.py:47-53`
**Issue:** `if not isinstance(limit, int) or limit <= 0` treats `True` as `1` (`isinstance(True, int)` is `True`), so `search_notes("e", limit=True)` returns exactly 1 result — a classic bool-is-int coercion bug. Conversely `limit=5.5` silently resets to `DEFAULT_LIMIT` (10) with no signal, discarding an explicit caller choice. Both are silent wrong-behavior paths on a public tool boundary. **WARNING.**
**Fix:**
```python
if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
    limit = DEFAULT_LIMIT
else:
    limit = min(limit, MAX_LIMIT)
```

## Info

### IN-01: Stale module docstring and misleading re-export comment

**File:** `src/kb_mcp/read_tools.py:1-7, 11`
**Issue:** Module docstring describes only "Keyword search and single-note retrieval tools (READ-01, READ-02)" but the module now exposes four tools (`search_notes`, `list_notes`, `get_tags`, `get_note`). Line 11 claims `parse_frontmatter` is a "re-exported contract import" (`# noqa: F401`), yet it is directly used at lines 129 and 165 — the comment is false and the `noqa` is unnecessary. Stale docs erode trust in the contract comments reviewers rely on.
**Fix:** Update the docstring to enumerate all four tools and drop the `(re-exported contract import)` comment / `noqa`.

### IN-02: Directory-listing + parse boilerplate duplicated 4x with divergent read paths

**File:** `src/kb_mcp/read_tools.py:57-63, 117-124, 152-159, 192-199`
**Issue:** All four tools repeat the `iterdir` + `is_file` + `suffix == ".md"` filter. Worse, `search_notes`/`get_note` read via `repo.read_note()` (validated path) while `list_notes`/`get_tags` reimplement raw `path.read_text` + `parse_frontmatter`, bypassing `validate_path`/`validate_filename` and any future logic added to `read_note`. Divergence risk: a behavior change in `read_note` silently applies to only half the tools.
**Fix:** Extract a `_iter_note_files(repo)` helper and have `list_notes`/`get_tags` call `repo.read_note(path.name)` (catching per-file skip errors) instead of raw reads.

### IN-03: Hardcoded default `limit=10` duplicates `DEFAULT_LIMIT`; empty/title messages echo raw input

**File:** `src/kb_mcp/read_tools.py:47, 55, 105, 109`
**Issue:** Signature default `limit: int = 10` hardcodes the value of `DEFAULT_LIMIT = 10` (line 14) — changing the constant silently diverges the default. Separately, the empty/miss messages echo raw `query` (`f"...'{query}'."`) rather than the normalized `q`, so `"  planner  "` echoes with whitespace and non-string input echoes as `None`/`123`. Minor consistency issue.
**Fix:** Use a sentinel default (`limit: int | None = None`, then `if limit is None: limit = DEFAULT_LIMIT`) or at minimum `limit: int = DEFAULT_LIMIT`; echo the stripped query in messages.

### IN-04: Tests do not meaningfully verify limit clamping, tag totals, or title lookup (lets CR-01 through)

**File:** `tests/test_read_tools.py:80-85, 167-174`
**Issue:** (a) `test_limit_clamp` seeds only 3 valid notes, so both `limit=500` and `limit=0` return 3 rows and `len(defaulted) == len(wide)` holds trivially — it cannot distinguish "clamped to 50" from "defaulted to 10". Needs >10 seeded notes to prove the clamp. (b) `test_get_tags_counts_and_order` asserts `sum(...) >= 4` when the seed deterministically yields 5 occurrences / 4 distinct tags — the loose bound lets regressions (dropped tags) pass. (c) No test calls `get_note` with a display title (`"Alpha Note"`), which is why CR-01 is undetected. Test-reliability gaps, not production bugs.
**Fix:** Seed 12+ notes in the clamp test and assert `len(wide) == 12`-ish vs `len(defaulted) == 10`; assert exact tag totals; add `test_get_by_title` covering `get_note("Alpha Note")` and case variant `"ALPHA NOTE"`.

---

_Reviewed: 2026-10-09T00:00:00Z_
_Reviewer: OpenCode (gsd-code-reviewer)_
_Depth: standard_
