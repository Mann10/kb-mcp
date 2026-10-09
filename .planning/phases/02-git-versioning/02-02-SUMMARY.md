---
phase: 02-git-versioning
plan: 02
subsystem: infra
tags: [dulwich, git, versioning, fail-open, audit-trail]

# Dependency graph
requires:
  - phase: 01-storage-foundation
    provides: [NoteRepository CRUD, atomic writes, filename/path validation]
  - phase: 02-git-versioning plan 01
    provides: [git_history.py fail-open collaborator, module-level porcelain monkeypatch target]
provides:
  - Automatic git commits on every NoteRepository write/delete (create/update/delete)
  - tests/test_git_history.py real-git suite (8 tests V-1..V-8 proving STOR-03)
affects: [phase-7-note-crud, phase-9-audit-logging]

# Tech tracking
tech-stack:
  added: []
  patterns: [always-on post-success hooks, lazy dulwich import at call site, branch-agnostic history assertions]

key-files:
  created: [tests/test_git_history.py]
  modified: [src/kb_mcp/storage.py]

key-decisions:
  - "Always-on hooks with no constructor flag (D-07; tmp repos are cheap so no disable switch needed)"
  - "update_note() untouched — D-06 delegation via write_note proven by using update_note in audit + no-empty-commit tests"

patterns-established:
  - "Hook ordering: existed-check before write, git call only after filesystem op fully succeeds (T-02-05)"
  - "Test helper pattern: open Repo, collect decoded (message, author, committer), close in finally"

requirements-completed: [STOR-03]

# Metrics
duration: 14min
completed: 2026-10-09
---

# Phase 2 Plan 2: Storage Hooks + Real-Git Tests Summary

**NoteRepository auto-commits every create/update/delete to dulwich git history with conventional messages, proven by 8 real-git tests covering audit order, single-file scope, fail-open, and empty-commit guard**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-10-09T15:36:00Z (approx, execution start)
- **Completed:** 2026-10-09T15:49:48Z
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments

- `write_note()` distinguishes create vs update via pre-write `path.exists()` check and calls `commit_note_file` as a bare fail-open statement after `_atomic_write` succeeds
- `delete_note()` calls `commit_note_deletion` as a bare statement after `unlink()` succeeds; `update_note()` untouched (commits via delegation)
- New `tests/test_git_history.py` (183 lines): 8 tests V-1..V-8 all green against per-test isolated `tmp_path` dulwich repos
- Full suite green: 64 passed (56 prior + 8 new), 2 skipped; manual audit-trail probe shows `note(create) → note(update) → note(delete)` sequence

## Task Commits

Each task was committed atomically:

1. **Task 1: Hook commits into write_note and delete_note** - `aa677dd` (feat)
2. **Task 2: Real-git tests for STOR-03 (V-1..V-8)** - `5547c14` (test)

**Plan metadata:** pending final docs commit (covers SUMMARY.md + STATE.md + ROADMAP.md + REQUIREMENTS.md)

## Files Created/Modified

- `src/kb_mcp/storage.py` - Two hook sites: `existed` pre-check + lazy `commit_note_file` call in `write_note`; lazy `commit_note_deletion` call in `delete_note`; `update_note` unchanged
- `tests/test_git_history.py` - 8 real-git tests: create/update/delete commits, audit-trail order + `porcelain.log` smoke, single-file scope, fail-open via commit monkeypatch, `.git`-invisible listing, no-empty-commit guard

## Decisions Made

- Always-on hooks, no constructor flag (plan discretion, D-07): fewer branches; tests use cheap tmp repos so no disable switch is needed
- `update_note()` left completely untouched per D-06; D-06 delegation is proven rather than assumed — the audit-trail test updates via `update_note()` and the no-empty-commit test exercises its identical-content path

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `porcelain.log` writes `str`, not bytes: the initial API probe with `io.BytesIO` raised `TypeError`, so the audit test uses `io.StringIO` (confirmed human-readable output contains all three messages). Probe-only finding, no plan change.
- `tests/test_integration.py` (untracked Phase-1 residue) left untouched per instructions; the full-suite gate collects it and it passes (64 passed includes its tests).

## Threat Flags

None - no new attack surface. Hook calls pass only the already-validated filename after filesystem success (T-02-05 holds); no hook in `update_note` so one-commit-per-operation holds (T-02-06); FileLocked retry + fail-open warning unchanged in the helper (T-02-08); history retention remains the accepted feature (T-02-07).

## Known Stubs

None - both hooks call the real `git_history` helper; all 8 tests assert against real commits. Grep for TODO/FIXME/placeholder/skip markers in the two plan files returns nothing.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- STOR-03 complete: SC-1 (create → one `note(create)` commit), SC-2 (update via `write_note` and `update_note` → new `note(update)` commit with changed blob), SC-3 (delete → `note(delete)` commit, file absent from HEAD tree), SC-4 (walker + `porcelain.log` show reverse-chronological audit trail)
- Phase 2 complete (02-01 + 02-02): Phase 7 write tools inherit versioning automatically via `NoteRepository`; Phase 9 can build audit logging on `get_walker`/`porcelain.log`
- No blockers or concerns

## Self-Check: PASSED

- `src/kb_mcp/storage.py` contains `commit_note_file`/`commit_note_deletion` hooks (read-verified)
- `tests/test_git_history.py` exists (183 lines, ≥80-line minimum)
- `git log --oneline` shows both task commits (`aa677dd`, `5547c14`)
- `uv run pytest tests/test_git_history.py -v` → 8 passed; `uv run pytest tests/ -x -q` → 64 passed, 2 skipped
- Manual audit probe → `[b'note(delete): demo', b'note(update): demo', b'note(create): demo']`

---
*Phase: 02-git-versioning*
*Completed: 2026-10-09*
