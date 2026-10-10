---
phase: 07-note-crud-operations
plan: 02
subsystem: api
tags: [write-tools, update-note, rename, atomic-commit, require_write, structured-returns]

# Dependency graph
requires:
  - phase: 07-note-crud-operations plan 01
    provides: create_note/delete_note write tools with _slugify_title + _resolve_stem helpers
  - phase: 03-token-model-middleware
    provides: require_write gate + INVALID/WRITE_DENIED messages
  - phase: 02-git-versioning
    provides: fail-open dulwich collaborator + one-commit-per-file convention
provides:
  - update_note gated write tool (content + metadata + rename, D-05..D-12)
  - Rename-aware storage.update_note with single-commit commit_note_rename path
  - Update/rename proofs including atomicity + single-commit + auth (34 tests)
affects: [08-tag-management, 09-integration-hardening]

# Tech tracking
tech-stack:
  added: []
  patterns: [validation-first-then-resolve at tool boundary, storage raises typed exceptions mapped to structured payloads at tool layer, function-local git_history imports mirroring existing hooks]

key-files:
  created: []
  modified: [src/kb_mcp/git_history.py, src/kb_mcp/storage.py, src/kb_mcp/write_tools.py, tests/test_write_tools.py, tests/test_integration.py]

key-decisions:
  - "Storage validates via NoteMetadata construction before any I/O; pydantic ValueError propagates to tool layer for structured mapping"
  - "Rename is write-new + unlink-old + one commit_note_rename commit; fail-open git never blocks the write"
  - "Lifecycle integration test updated for rename move (delete targets the new stem)"

patterns-established:
  - "Tool-layer pre-checks (collision, validation) run before storage delegation; storage guards remain as the race-safe backstop"
  - "No-op update returns success with 'No changes' message and byte-identical file content"

requirements-completed: [WRITE-02, WRITE-03]

# Metrics
duration: 3min
completed: 2026-10-10
---

# Phase 7 Plan 2: Update Tool with Rename Summary

**require_write-gated update_note with content/metadata/rename support, single-commit atomic storage rename, and 19 new proofs (34 total) — full suite green at 183 passed**

## Performance

- **Duration:** 3 min
- **Started:** 2026-10-10T11:50:44+05:30
- **Completed:** 2026-10-10T11:53:04+05:30
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- `commit_note_rename` in git_history.py stages add + delete in exactly one `note(update)` commit, fail-open with single FileLocked retry per op
- Storage `update_note` rewritten: validation-first via `NoteMetadata`, `_slugify_stem` + `validate_filename` path guard, `FileExistsError` collision guard, atomic write-new + unlink-old rename path
- `update_note` tool in write_tools.py: no-op success, boundary validation before resolution, rename-collision pre-check with `Rename rejected`, typed-exception mapping, new-filename echo per D-12
- 19 appended tests proving body/tags/created updates, no-op (missing + byte-identical), all validation branches, rename move, collision intactness, rename+body atomicity, delta-1 single-commit, per-tool auth denials

## task Commits

Each task was committed atomically:

1. **task 1: Add single-commit rename path to git_history + storage** - `97f42c0` (feat)
2. **task 2: Add update_note tool + rename/atomicity proofs** - `cb7e9d9` (feat)

**Plan metadata:** (docs commit follows STATE/ROADMAP updates)

## Files Created/Modified

- `src/kb_mcp/git_history.py` - Added `commit_note_rename` (single `note(update)` commit over add + remove, fail-open)
- `src/kb_mcp/storage.py` - Added `import re` + `_slugify_stem`; rewrote `update_note` with validation-first, collision guard, atomic rename path
- `src/kb_mcp/write_tools.py` - Appended `@require_write update_note` (no-op, validation, resolution, collision pre-check, delegation, D-12/D-16 payload)
- `tests/test_write_tools.py` - Appended 19 tests (15 → 34 passing)
- `tests/test_integration.py` - One-line fix: lifecycle delete targets the renamed stem (was untracked in tree; committed here)

## Decisions Made

- Storage constructs `NoteMetadata` immediately for validation and reuses the validated object downstream, so tool-layer error mapping sees a single exception style (pydantic `ValueError` / `InvalidTypeError`).
- `created` is validated at the tool boundary with `date.fromisoformat(created.strip())` but passed through verbatim to storage, which re-validates — no silent normalization, matching create_note's strictness without duplicating its defaulting.
- `FileExistsError` from storage maps to a `Rename rejected`-flavored exists payload, keeping the tool pre-check as the common path and the storage guard as the race backstop.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Lifecycle integration test encoded pre-rename same-file behavior**
- **Found during:** task 2 (full-suite verification)
- **Issue:** `tests/test_integration.py::TestNoteLifecycle::test_full_lifecycle` calls `update_note` with a new title then deletes the OLD filename. Under the plan-mandated D-09 rename, the file moves to `updated-lifecycle-note.md`, so the delete raised `NoteNotFoundError` (1 failed, 182 passed).
- **Fix:** Delete targets `updated-lifecycle-note.md` with a comment noting the rename move. No production-code change.
- **Files modified:** tests/test_integration.py
- **Verification:** `pytest -q` → 183 passed, 2 skipped (pre-existing skips)
- **Committed in:** cb7e9d9 (task 2 commit)

**2. [Rule 3 - Blocking] test_integration.py was untracked in the working tree**
- **Found during:** task 2 (commit staging)
- **Issue:** `tests/test_integration.py` showed as `??` untracked — created by prior work but never committed. The plan requires the full suite green, which depends on this file, so it had to be committed for traceability.
- **Fix:** Staged and committed alongside the task 2 changes (single non-deletion line edit of mine; remainder as found).
- **Files modified:** tests/test_integration.py (committed as new file)
- **Verification:** `git log --oneline` shows cb7e9d9 with `create mode` for the file; no deletions in commit
- **Committed in:** cb7e9d9 (task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both required for the plan's own success criteria (full suite green, committed state). No scope creep — no new features beyond D-05..D-12.

## Issues Encountered

- Windows PowerShell has no `tail`; used `Select-Object -Last N` for all output windowing. No impact on results.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 7 complete (07-01 create/delete + 07-02 update/rename): all four CRUD tools gated, structured payloads per D-16, single-commit git lineage throughout.
- Ready for Phase 8 (Tag Management) — `update_note` tags-field semantics are clean for tag add/remove to build on.
- No blockers. Full suite green: 183 passed, 2 skipped (pre-existing skips).

## Self-Check: PASSED

- FOUND: src/kb_mcp/git_history.py (def commit_note_rename, note(update))
- FOUND: src/kb_mcp/storage.py (def _slugify_stem, commit_note_rename, already exists)
- FOUND: src/kb_mcp/write_tools.py (def update_note, 3x @require_write, No changes, Rename rejected, 0 direct-I/O, 0 verify_token/TokenStore()
- FOUND: tests/test_write_tools.py (new_title, No changes, 34 passed)
- FOUND: 97f42c0
- FOUND: cb7e9d9
- Plan verification re-run: `pytest -q` 183 passed, 2 skipped; `@require_write` count 3; no regressions in Phases 1-6.

---
*Phase: 07-note-crud-operations*
*Completed: 2026-10-10*
