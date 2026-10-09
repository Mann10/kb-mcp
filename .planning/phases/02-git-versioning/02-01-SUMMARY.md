---
phase: 02-git-versioning
plan: 01
subsystem: infra
tags: [dulwich, git, fail-open, versioning]

# Dependency graph
requires:
  - phase: 01-storage-foundation
    provides: [NoteRepository CRUD, atomic writes, filename/path validation]
provides:
  - dulwich>=1.2.17 dependency (pure-Python git, no binary required)
  - src/kb_mcp/git_history.py fail-open collaborator (ensure_repo + commit_note_file + commit_note_deletion)
affects: [02-02 storage hooks + tests, phase-7-note-crud, phase-9-audit-logging]

# Tech tracking
tech-stack:
  added: [dulwich>=1.2.17 (urllib3==2.8.0 transitive)]
  patterns: [fail-open collaborator, guarded-import None-sentinel, single-path staging, staged-emptiness guard]

key-files:
  created: [src/kb_mcp/git_history.py]
  modified: [pyproject.toml, uv.lock]

key-decisions:
  - "History-from-first-change: no bulk commit of pre-existing notes at init (D-12 discretion)"
  - "ensure_repo writes *.tmp .gitignore so crash-residue temp files are never stageable (P-10)"
  - "Single FileLocked retry with 0.1s sleep, proportionate to single-writer KB scale (D-15)"

patterns-established:
  - "Guarded module-level dulwich import with None-sentinel keeps module importable without dulwich (D-14)"
  - "Module-level porcelain attribute doubles as monkeypatch target for fail-open tests"

requirements-completed: []  # STOR-03 spans 02-01 + 02-02; completes when 02-02 wires hooks + tests

# Metrics
duration: 2min
completed: 2026-10-09
---

# Phase 2 Plan 1: Git History Collaborator Summary

**Fail-open dulwich collaborator (`ensure_repo` + `commit_note_file` + `commit_note_deletion`) with guarded import, single-file staging, empty-commit guard, and explicit mechanism identity**

## Performance

- **Duration:** ~2 min (wall clock 20:59:56Z-21:01:38Z)
- **Started:** 2026-10-09T20:59:56Z
- **Completed:** 2026-10-09T21:01:38Z
- **Tasks:** 2
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments

- `dulwich>=1.2.17` declared in pyproject.toml and resolved via uv (`dulwich==1.2.17 + urllib3==2.8.0`); `dulwich.__version__ == (1, 2, 17)` confirmed under `uv run`
- New `src/kb_mcp/git_history.py` (104 lines) exporting `ensure_repo`, `commit_note_file`, `commit_note_deletion` with fixed `kb-mcp <kb-mcp@localhost>` author/committer bytes
- All three must-have truths verified hands-on: fresh dir gains repo + `.gitignore` on first call with second call a no-op; create/update/delete produce exactly `note(create)/note(update)/note(delete): <stem>` commits; no-op rewrite produces no commit; poisoned-import path warns and returns without raising
- Full existing suite green after changes: 56 passed, 2 skipped

## Task Commits

Each task was committed atomically:

1. **Task 1: Add dulwich dependency** - `cfc17f0` (feat)
2. **Task 2: Create git_history.py fail-open collaborator** - `eea94c7` (feat)

**Plan metadata:** pending final docs commit (covers SUMMARY.md + STATE.md + ROADMAP.md)

## Files Created/Modified

- `src/kb_mcp/git_history.py` - Fail-open dulwich wrapper: guarded import, lazy init with init-race tolerance, single-path add/remove, FileLocked single-retry, staged-emptiness guard, explicit author/committer, broad fail-open catch with filename-context warning
- `pyproject.toml` - Added `dulwich>=1.2.17` to dependencies (no urllib3 pin, no Rust extensions per D-01/D-02)
- `uv.lock` - Resolver output for dulwich 1.2.17 + urllib3 2.8.0

## Decisions Made

- History-from-first-change for pre-existing notes (D-12 discretion): zero extra code, documented in module docstring; a bulk `note(init)` commit would violate one-file-per-commit (D-05)
- `.gitignore` (`*.tmp`) written idempotently by `ensure_repo` on every call, not just fresh init, so repos predating this change also gain the guard
- Single FileLocked retry (`time.sleep(0.1)`) rather than exponential backoff — proportionate to single-writer KB scale per RESEARCH Pitfall 8 / assumption A1

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Windows PowerShell 5.1 environment lacks `head`/`tail` — used `Select-Object`-free alternatives (`Test-Path`, direct output). No impact on deliverables.
- `tests/test_integration.py` (untracked Phase-1 residue) left untouched per instructions; full suite run includes it and stays green.

## Threat Flags

None - no new attack surface. All four STRIDE mitigations from the plan's threat register are implemented: repo-relative `paths=[filename]` only (T-02-01), stem-only commit messages from validated filenames (T-02-02), `*.md`-only staging path with `.gitignore` written solely by `ensure_repo` (T-02-03), guarded import + fail-open returns (T-02-04).

## Known Stubs

None - every function is fully wired to dulwich porcelain and exercised end-to-end (create/update/delete/no-op/poisoned-import).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 02-02 (storage hooks + real-git tests): `storage.py` needs only the ~10-line diff calling `commit_note_file`/`commit_note_deletion` post-write/post-unlink, plus `tests/test_git_history.py` (V-1..V-8).
- STOR-03 remains open until 02-02 wires the hooks — this plan delivers the collaborator only.
- `kb_mcp.git_history.porcelain` module attribute is available as the 02-02 test 6 monkeypatch target (W-1 fix).

## Self-Check: PASSED

- `src/kb_mcp/git_history.py` exists (Test-Path True); `pyproject.toml` contains dulwich pin
- `git log --grep="02-01"` returns both task commits (`cfc17f0`, `eea94c7`)
- Final import check `from kb_mcp.git_history import ensure_repo, commit_note_file, commit_note_deletion` succeeds in a fresh process

---
*Phase: 02-git-versioning*
*Completed: 2026-10-09*
