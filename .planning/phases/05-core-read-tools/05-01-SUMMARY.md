---
phase: 05-core-read-tools
plan: 01
subsystem: api
tags: [keyword-search, read-tools, require_read, snippets, auth-gating]

# Dependency graph
requires:
  - phase: 03-token-model-middleware
    provides: require_read decorator and fail-closed token verification
  - phase: 01-storage-foundation
    provides: NoteRepository read paths with path validation and silent malformed-skip
provides:
  - search_notes keyword search across body+title+stem+tags with snippets
  - get_note case-insensitive single-note retrieval with structured fields
affects: [06-advanced-filtering, 07-note-crud, 09-integration-hardening]

# Tech tracking
tech-stack:
  added: []
  patterns: [require_read-gated tool functions, structured-dict returns with message field, module-level configure_default_repo test injection]

key-files:
  created: [src/kb_mcp/read_tools.py, tests/test_read_tools.py]
  modified: []

key-decisions:
  - "Search iterates notes_dir stems + read_note per note (list_notes drops stems, so direct stem scan was required for stem matching)"
  - "Malformed-note read failures in get_note map to structured not-found instead of raising"

patterns-established:
  - "Read tools never touch TokenStore/verify_token — auth lives entirely in require_read"
  - "Expected empty states return structured payloads with a message field, never bare strings or exceptions"

requirements-completed: [READ-01, READ-02]

# Metrics
duration: 4min
completed: 2026-10-09
---

# Phase 5 Plan 1: Core Read Tools Summary

**Keyword search with keyword-in-context snippets plus case-insensitive get-note, both gated behind require_read with structured-dict returns**

## Performance

- **Duration:** 4 min
- **Started:** 2026-10-09T17:22:35Z
- **Completed:** 2026-10-09T17:26:30Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `search_notes` matches case-insensitive substrings across body + title + filename stem + tags, ranks body > title/stem > tags-only with `created` tiebreak, clamps limit to 1..50 (default 10)
- `get_note` resolves titles case-insensitively with single trailing `.md` tolerance, returns structured fields (filename/title/tags/created/body), missing maps to structured not-found
- 13 seeded-repo proofs green covering hits, miss payloads, clamp, case-insensitivity, suffix tolerance, malformed-skip, and bogus/None auth denials
- Full suite regression clean: 114 passed, 2 skipped

## Task Commits

Each task was committed atomically:

1. **task 1: Create read_tools module with search_notes + get_note contracts** - `24c4382` (feat)
2. **task 2: Prove search + get behavior with seeded repo tests** - `addeb75` (feat)

**Plan metadata:** pending final docs commit (see STATE/ROADMAP updates below)

## Files Created/Modified

- `src/kb_mcp/read_tools.py` - `search_notes` + `get_note` gated tools, `DEFAULT_LIMIT`/`MAX_LIMIT`/`SNIPPET_CONTEXT` constants, `configure_default_repo` injection
- `tests/test_read_tools.py` - Seeded fixtures (3 valid + 1 malformed note) with 13 behavior/auth proofs

## Decisions Made

- Search stem enumeration scans `repo.notes_dir` for `.md` stems instead of `repo.list_notes()` because `list_notes()` returns `NoteMetadata` without stems — stem matching (D-01) requires the stem, so a directory scan plus per-note `read_note()` was the only delegation-preserving option.
- `get_note` maps any `read_note` failure (not just `NoteNotFoundError`) to the structured not-found payload so malformed-note edge cases never surface tracebacks to clients.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Seeded notes needed `.md` filenames**
- **Found during:** task 2 (seeded repo tests)
- **Issue:** Plan action wrote `repository.write_note("alpha-note", ...)` but `validate_filename` requires the `.md` suffix (`SAFE_FILENAME = ^[a-z0-9][a-z0-9_-]*\.md$`), so all 13 tests errored in fixture setup
- **Fix:** Seeded as `"alpha-note.md"`, `"beta-note.md"`, `"gamma-note.md"` (returned `Note.filename` stems unchanged, so all downstream assertions hold verbatim)
- **Files modified:** tests/test_read_tools.py
- **Verification:** `pytest tests/test_read_tools.py -q` → 13 passed
- **Committed in:** addeb75 (task 2 commit)

**2. [Rule 3 - Blocking] Search stem source adjusted from `list_notes()` to directory scan**
- **Found during:** task 1 (read_tools implementation)
- **Issue:** Plan said "iterate via `repo.list_notes()` stems" but `list_notes()` returns `list[NoteMetadata]` with no stem/filename field, so stems are unrecoverable from it
- **Fix:** Enumerate `.md` stems via `repo.notes_dir.iterdir()` (same idiom `get_note` uses), then `repo.read_note(stem + ".md")` per note inside try/except → skip malformed silently. Still delegates all parsing/validation to `NoteRepository`
- **Files modified:** src/kb_mcp/read_tools.py
- **Verification:** Interface grep gate (`NoteRepository|read_note|list_notes` delegation, no `verify_token`/`TokenStore(`) passes; search proofs green
- **Committed in:** 24c4382 (task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Both required for the plan to function at all; no scope creep — behavior, payloads, and gates match the plan exactly.

## Issues Encountered

None - plan executed as written apart from the two blocking deviations above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- READ-01 and READ-02 complete; ready for 05-02 (list-notes + tags browse, READ-03/READ-04)
- `configure_default_repo` injection pattern available for 05-02 tests; search signature left extensible for Phase 6 filters

---
*Phase: 05-core-read-tools*
*Completed: 2026-10-09*

## Self-Check: PASSED

- All created files exist on disk (`src/kb_mcp/read_tools.py`, `tests/test_read_tools.py`, SUMMARY)
- Both task commits present in git log (`24c4382`, `addeb75`)
- Plan verification gates re-run green: `pytest tests/test_read_tools.py -q` (13 passed), `@require_read` count = 2, `verify_token|TokenStore(` count = 0
