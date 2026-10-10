---
phase: 08-tag-management-templates
plan: 01
subsystem: api
tags: [tags, write-tools, require_write, idempotent, case-insensitive]

# Dependency graph
requires:
  - phase: 07-note-crud-operations
    provides: write_tools module with _resolve_stem, create/update/delete, require_write gating
provides:
  - add_tags + remove_tags gated tools with case-insensitive merge in write_tools.py
  - tests/test_tag_tools.py seeded proofs (merge, idempotency, validation, auth)
affects: [08-02 templates plan, phase 9 integration hardening]

# Tech tracking
tech-stack:
  added: []
  patterns: [read-modify-write via repo.update_note single note(update) commit, structured invalid-tags payload, idempotent No-changes success]

key-files:
  created: [tests/test_tag_tools.py]
  modified: [src/kb_mcp/write_tools.py]

key-decisions:
  - "Shared _validate_tag_list helper enforces list-of-str, len<100, whitespace-only reject with Invalid tags message"
  - "add preserves caller casing verbatim stripped; dedupe/match via strip().lower() symmetric for remove"
  - "Single-commit atomicity proven via dulwich walker count + note(update) message"

patterns-established:
  - "Tag merge pattern: seen-set + merged-list with in-list dupe skip"
  - "Idempotent no-change success shape mirrors Phase 7 update no-op"

requirements-completed: [WRITE-05, WRITE-06]

# Metrics
duration: 1min
completed: 2026-10-10
---

# Phase 8 Plan 01: Tag Tools Summary

**add_tags + remove_tags with idempotent case-insensitive merge behind require_write, proven by 20 isolated-repo tests**

## Performance

- **Duration:** 1 min
- **Started:** 2026-10-10T06:39:36Z
- **Completed:** 2026-10-10T06:40:34Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `add_tags`: list-at-once add, caller-casing verbatim store, case-insensitive dedupe, idempotent duplicate skip with `No changes` message, single `note(update)` commit
- `remove_tags`: case-insensitive match (removing `work` drops `Work`), idempotent missing skip with `No changes` message, single-commit delegation
- Both tools: structured `Invalid tags` validation (non-list / non-str / len>=100 / whitespace-only), structured not-found, `@require_write` gated with per-tool auth proofs
- 20 new tests green; 34 existing write-tools tests still green; zero direct file I/O in write_tools.py

## task Commits

Each task was committed atomically:

1. **task 1: Add add_tags + remove_tags tools to write_tools** - `575dddb` (feat)
2. **task 2: Prove add/remove behavior with isolated repo tests** - `bc14e81` (test)

**Plan metadata:** `docs(08-01)` commit completing the plan (see git log)

## Files Created/Modified

- `src/kb_mcp/write_tools.py` - Appended INVALID_TAGS_MESSAGE, _validate_tag_list, add_tags, remove_tags (no changes to existing functions)
- `tests/test_tag_tools.py` - 20 proofs: add hit, idempotent/case/in-list dupes, suffix+case resolution, missing, 4 invalid shapes x2 tools, remove hit/case/missing, single-commit, per-tool auth denials

## Decisions Made

- Shared `_validate_tag_list` helper mirrors create_note/update_note boundary validation (raw `len(t) >= 100`, whitespace-only rejected) so both tools stay consistent.
- Add stores caller's stripped casing verbatim; dedupe key is `strip().lower()` — preserves D-05 display while matching D-06 semantics.
- Remove builds `drop` set from stripped-lowered incoming and filters stored tags by `strip().lower()` — symmetric D-08 behavior.
- Success messages: add `Added N tag(s) to 'title'.`, remove `Removed N tag(s) from 'title'.`; no-change messages contain `No changes` per acceptance gate.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 08-02 (templates: TEMPLATES catalog + create_from_template on same write_tools module).
- WRITE-05/WRITE-06 correctness proofs in place; Phase 9 MCP transport hardening can rely on structured payloads.

---
*Phase: 08-tag-management-templates*
*Completed: 2026-10-10*

## Self-Check: PASSED
