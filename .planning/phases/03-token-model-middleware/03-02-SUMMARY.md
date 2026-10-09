---
phase: 03-token-model-middleware
plan: 02
subsystem: auth
tags: [middleware, decorators, scopes, pytest, fail-closed]

# Dependency graph
requires:
  - phase: 03-token-model-middleware (plan 01)
    provides: [TokenType/TokenEntry/TokenStore hashed token foundation, AuthenticationError + AuthorizationError, tmp_path token fixtures]
provides:
  - Transport-agnostic verify_token + require_read/require_write decorators with strict verify-scope-check-invoke ordering
  - SC-1..SC-4 automated proofs (read-denied-write with zero side effects, rw-allowed-both, invalid/missing rejection, every-call re-verification)
affects: [Phase 4 CLI token management, Phase 5/7 tool gates adopting the decorators, Phase 9 MCP transport adapter]

# Tech tracking
tech-stack:
  added: []
  patterns: [decorator-based scope gates keyed on token kwarg, module-level default store holder, fail-closed deny on misconfiguration]

key-files:
  created: [src/kb_mcp/middleware.py, tests/test_middleware.py]
  modified: []

key-decisions:
  - "Shared _gate helper parameterized by scope + denial message so require_read/require_write cannot drift in ordering"
  - "Reworded module docstring to avoid lowercase transport-SDK substrings so the plan's zero-transport-import grep gate passes literally"

patterns-established:
  - "Gated tools declare token as keyword-or-positional-last and _store for injection; decorators extract token by keyword only"
  - "Deny paths never invoke the wrapped function (asserted via module-level calls list)"

requirements-completed: [AUTH-01, AUTH-02]

# Metrics
duration: ~6min
completed: 2026-10-09
---

# Phase 03 Plan 02: Token Middleware Summary

**Transport-agnostic verify-then-scope-check-then-invoke decorators proving read-denied-write, rw-allowed-both, and every-call re-verification — zero new dependencies**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-10-09T16:24:00Z
- **Completed:** 2026-10-09T16:29:41Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `verify_token` fail-closed lookup: None/blank short-circuits without store touch, unknown hashes warn without secret material, success stamps `update_last_used`
- `require_read` / `require_write` enforce strict ordering (store-present → verify → scope-check → invoke); misconfigured (no store) denies, never opens
- 9-test proof suite covers SC-1 (read allows read, denied write with empty `calls`), SC-2 (rw allows both), SC-3 (bogus/None/omitted denied everywhere), SC-4 (post-revoke denial without tool change, zero auth refs in dummy bodies)
- Full suite green: 88 passed, 2 skipped (baseline 79 passed + 9 new, zero regressions)
- Ad-hoc matrix confirmed live: read×read-gate ok, read×write-gate denied with exact message, rw×both ok, bogus/None×both denied

## task Commits

Each task was committed atomically:

1. **task 1: Create middleware.py verification + decorators** - `2b10372` (feat)
2. **task 2: SC-1..SC-4 middleware proofs (GREEN + gate)** - `e383416` (test)

## Files Created/Modified

- `src/kb_mcp/middleware.py` (created, 103 lines) - `verify_token`, `require_read`, `require_write`, `configure_default_store`, scope/message constants, `READ_SCOPE`/`WRITE_SCOPE`
- `tests/test_middleware.py` (created, 123 lines) - `dummy_read`/`dummy_write` zero-auth-code tools + 9 scope/denial/revocation/corrupt/unconfigured/default-store tests

## Decisions Made

- **Shared `_gate(fn, scope, message)` helper:** both decorators delegate to one ordering implementation so verify→scope-check→invoke cannot drift between read and write paths; `functools.wraps` preserves tool identity for Phase 9 adaptation.
- **Docstring rewording for the literal grep gate:** "No transport-SDK imports" phrasing keeps the zero-`mcp`-substring gate green while preserving intent (see deviations).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Docstring tripped the zero-transport-import grep gate**
- **Found during:** task 1 (acceptance verification)
- **Issue:** Module docstring contained lowercase `mcp`/`fastmcp` substrings ("No ``mcp``/``fastmcp`` imports here"), so the plan's `grep -c "mcp\|fastmcp\|print("` gate returned 2 instead of 0.
- **Fix:** Reworded to "No transport-SDK imports here — Phase 9 adapts these decorators to the transport layer"; gate now returns 0, no code behavior changed.
- **Files modified:** src/kb_mcp/middleware.py
- **Verification:** transport-or-print-count:0, import prints `ok`
- **Committed in:** 2b10372 (task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 correctness-of-gate phrasing)
**Impact on plan:** Cosmetic docstring wording only; zero behavior/scope change.

## Issues Encountered

- Ad-hoc `python -c` matrix check failed with `SyntaxError` (decorators cannot follow semicolons in a one-liner) — reran as a temp script outside the workspace, matrix fully confirmed, temp file removed. No impact on deliverables.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for Phase 5/7 tool adoption: gate any tool with `@require_read` / `@require_write`, pass `token` by keyword and `_store` explicitly (or set one default via `configure_default_store`).
- Ready for Phase 9 transport adaptation: decorators key on the `token` kwarg with scope strings (`notes:read`/`notes:write`) matching the future access-token shape; no decorator changes needed.
- No blockers. Pre-existing untracked `tests/test_integration.py` and orchestrator-owned `STATE.md`/`ROADMAP.md` working-copy modifications were left untouched.

## Self-Check: PASSED

- `src/kb_mcp/middleware.py` (103 lines, ≥60) FOUND; `tests/test_middleware.py` (123 lines, ≥80) FOUND
- Commits `2b10372` and `e383416` present in `git log`, both on top of base `ddd32ea`
- Acceptance re-verified post-commit: exact denial strings present, transport-grep 0, dummy-body auth refs 0, middleware suite 9 passed, full suite 88 passed / 2 skipped

---
*Phase: 03-token-model-middleware*
*Completed: 2026-10-09*
