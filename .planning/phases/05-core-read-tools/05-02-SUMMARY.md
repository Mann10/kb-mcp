---
phase: 05-core-read-tools
plan: 02
subsystem: api
tags: [list-notes, tags-browse, require_read, auth-gating, metadata]

# Dependency graph
requires:
  - phase: 05-core-read-tools plan 01
    provides: read_tools module with require_read-gated search/get plus seeded fixtures and configure_default_repo injection
  - phase: 03-token-model-middleware
    provides: require_read decorator and fail-closed token verification
  - phase: 01-storage-foundation
    provides: NoteRepository read paths with path validation and silent malformed-skip
provides:
  - list_notes metadata-only listing (created-ascending, malformed skipped, structured empty message)
  - get_tags frequency-sorted case-normalized tag browse with counts
  - all-four-tools auth-denial proofs (bogus/missing/revoked)
affects: [06-advanced-filtering, 07-note-crud, 09-integration-hardening]

# Tech tracking
tech-stack:
  added: []
  patterns: [require_read-gated tool functions, structured-dict returns with message field, module-level configure_default_repo test injection]

key-files:
  created: []
  modified: [src/kb_mcp/read_tools.py, tests/test_read_tools.py]

key-decisions:
  - "Tag scan sorted by filename so first-seen display form is deterministic across filesystems"
  - "Seed created dates aligned to 2026-01-01/2026-02-01/2026-03-01 per plan instead of duplicating fixtures"

patterns-established:
  - "Read tools never touch TokenStore/verify_token — auth lives entirely in require_read"
  - "Expected empty states return structured payloads with a message field, never bare strings or exceptions"

requirements-completed: [READ-03, READ-04]

# Metrics
duration: 2min
completed: 2026-10-09
---

# Phase 5 Plan 2: List + Tags Read Tools Summary

**Metadata-only list_notes plus frequency-sorted case-normalized get_tags, both require_read-gated with all-four-tools bogus/missing/revoked denial proofs**

## Performance

- **Duration:** 2 min
- **Started:** 2026-10-09T22:58:47Z
- **Completed:** 2026-10-09T23:00:43Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `list_notes` returns full metadata per note (filename/title/tags/created, no body key) in `created` ascending, skips malformed notes silently, empty KB returns `{"notes": [], "message": "No notes found."}`
- `get_tags` aggregates tags case-insensitively (`Work` + `work` → single `work:2` entry), emits `{"tag", "count"}` pairs sorted by count desc then tag asc, empty KB returns `{"tags": [], "message": "No tags found."}`
- All four read tools deny bogus/missing tokens (`AuthenticationError: Invalid or missing token`) plus revoked-token denial on `list_notes`, proven by a parametrized sweep — no per-tool auth code anywhere
- Full suite regression clean: 123 passed, 2 skipped (was 114 passed before this plan; +9 new tests)

## Task Commits

Each task was committed atomically:

1. **task 1: Add list_notes + get_tags tools to read_tools module** - `5413b10` (feat)
2. **task 2: Prove list/tags behavior and all-four auth gating** - `db86e19` (feat)

**Plan metadata:** pending final docs commit (see STATE/ROADMAP updates below)

## Files Created/Modified

- `src/kb_mcp/read_tools.py` - Appended `list_notes` + `get_tags` (`@require_read`, keyword-only `token`/`_store`, structured hit/empty payloads); `get_tags` scan sorted by filename for deterministic display forms
- `tests/test_read_tools.py` - Reused seeded fixtures (dates aligned to 2026-01-01/02-01/03-01); added list shape/order/empty tests, tag count/order/empty tests, parametrized 4-tool bogus/missing sweep, revoked-token denial

## Decisions Made

- Tag scan iterates files sorted by filename so the first-seen display form (`work` from alpha-note, not `Work` from beta-note) is deterministic — raw `iterdir()` order is filesystem-dependent, which would make the pinned display form flaky.
- Seed `created` dates updated in place to 2026-02-01/2026-03-01 per the plan (instead of duplicating fixtures) — no existing assertions depended on the old 01-02/01-03 dates.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Tag display form was filesystem-order-dependent**
- **Found during:** task 2 (tag proof design)
- **Issue:** Plan pins display form first-seen `"work"`, but `get_tags` scanned `iterdir()` order, which is filesystem-dependent — on some filesystems beta-note could enumerate first, yielding `"Work"` and a flaky/failing proof
- **Fix:** Sort the scan by filename (`sorted(files, key=lambda p: p.name)`) before the counting pass; alpha-note always seeds the display form. Output order unchanged (still `(-count, tag)` sorted)
- **Files modified:** src/kb_mcp/read_tools.py
- **Verification:** `pytest tests/test_read_tools.py -q` → 22 passed, `out["tags"][0] == {"tag": "work", "count": 2}`
- **Committed in:** db86e19 (task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minimal determinism fix required for the plan's own pinned display-form assertion to hold reliably; no scope creep — payloads, gates, and ordering match the plan exactly.

## Issues Encountered

None - plan executed as written apart from the one determinism fix above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- READ-03 and READ-04 complete; Phase 5 (core-read-tools) is fully delivered — all four read tools gated, proven, and regression-clean
- Ready for Phase 6 (Advanced Filtering), which layers tag + date-range filters on the keyword search; search signature left extensible per 05-01

---
*Phase: 05-core-read-tools*
*Completed: 2026-10-09*

## Self-Check: PASSED

- All files exist on disk (`src/kb_mcp/read_tools.py`, `tests/test_read_tools.py`, SUMMARY)
- Both task commits present in git log (`5413b10`, `db86e19`)
- Plan verification gates re-run green: `pytest tests/test_read_tools.py -q` (22 passed), full `pytest -q` (123 passed, 2 skipped), `@require_read` count = 4, `verify_token|TokenStore(` count = 0, `verify_token` in tests = 0
