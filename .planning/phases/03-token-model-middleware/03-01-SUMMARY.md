---
phase: 03-token-model-middleware
plan: 01
subsystem: auth
tags: [tokens, sha256, pydantic, pytest, fail-closed]

# Dependency graph
requires:
  - phase: 02-git-versioning
    provides: [atomic-write pattern, pydantic/env-override conventions reused by TokenStore]
provides:
  - Typed hashed token foundation (TokenType, TokenEntry, TokenStore) for Plan 02 middleware
  - AuthenticationError + AuthorizationError typed exceptions for middleware denial paths
  - tmp_path-isolated token fixtures (token_store, read/rw pairs) reused by test_middleware.py
affects: [03-02 middleware plan, Phase 4 CLI token management, Phase 5/7 tool gates, Phase 9 hardening]

# Tech tracking
tech-stack:
  added: []
  patterns: [hash-only secret persistence, type-derived scopes, fail-closed load, fail-open telemetry]

key-files:
  created: [src/kb_mcp/auth.py, tests/test_auth.py]
  modified: [src/kb_mcp/errors.py, tests/conftest.py]

key-decisions:
  - "Deferred (function-local) auth imports in conftest fixtures so Wave 0 RED breaks only test_auth.py"
  - "TokenStore constructor stays write-free (no auto-load); load() classmethod owns all disk reads"
  - "Unparsable expires_at denies (fail-closed) rather than warn-and-allow"

patterns-established:
  - "Hash-only persistence: SHA-256 hex on disk, raw secret returned once from add_token"
  - "Scopes derived from TokenType property; TokenEntry.scopes delegates, nothing stored independently"
  - "Fail-closed lookup (any doubt returns None) vs fail-open telemetry (update_last_used never raises)"

requirements-completed: [AUTH-01]

# Metrics
duration: 3min
completed: 2026-10-09
---

# Phase 03 Plan 01: Token Model + Store Summary

**Typed SHA-256-hashed token foundation with fail-closed TokenStore, scope-deriving TokenType, and 15-test proof suite — zero new dependencies**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-10-09T21:45:58Z
- **Completed:** 2026-10-09T21:48:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- `TokenType` distinguishes `read` vs `read_write` with exact `notes:read` / `notes:write` scope strings
- `TokenEntry` carries nullable `revoked_at` / `expires_at` / `last_used_at` for Phase 4 without reshaping
- `TokenStore` defaults to `~/knowledge-base/.tokens.json`, honors `KB_TOKENS_FILE`, fails closed on missing/corrupt files
- Zero plaintext on disk, in repr (`Field(repr=False)` on `key_hash`), or in logs (prefix...suffix only); zero transport imports
- Full suite green: 79 passed, 2 skipped (baseline was 64 passed, 2 skipped; +15 new auth tests)

## task Commits

Each task was committed atomically:

1. **task 1: Auth errors + test scaffold + fixtures (Wave 0)** - `9b2f6af` (test)
2. **task 2: Create auth.py token model + store (GREEN)** - `80a8672` (feat)

## Files Created/Modified

- `src/kb_mcp/auth.py` (created, 204 lines) - TokenType, TokenEntry, TokenStore, `_hash_token`/`generate_token`/`utc_now_iso` helpers
- `tests/test_auth.py` (created, 175 lines) - 15 tests: scopes, roundtrip, no-plaintext, missing/corrupt, unknown/revoked/expired, repr secrecy, generation, telemetry
- `src/kb_mcp/errors.py` (modified) - Added `AuthenticationError` (default "Invalid or missing token.") and `AuthorizationError` in existing style
- `tests/conftest.py` (modified) - Added `token_store_path`, `token_store`, `read_token_pair`, `read_write_token_pair` fixtures via real `add_token()` path

## Decisions Made

- **Deferred conftest imports:** token fixtures import `kb_mcp.auth` inside the fixture body, not at module top, so the Wave 0 RED phase (auth.py absent) fails only `test_auth.py` collection and never breaks Phase 1/2 suites sharing the global conftest.
- **Constructor never reads disk:** `TokenStore()` starts empty; all file I/O lives in `load()`/`save()`. Keeps construction side-effect-free except parent-dir provisioning (mirrors `NoteRepository`).
- **Unparsable `expires_at` denies:** a hand-edited non-ISO expiry string returns `None` with a warning, matching the corrupt-store fail-closed posture rather than treating garbage as never-expires.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Deferred auth imports in conftest fixtures**
- **Found during:** task 1 (fixture design)
- **Issue:** A top-level `from kb_mcp.auth import ...` in the shared `tests/conftest.py` would break collection of every existing suite during Wave 0 RED (auth.py not yet created), violating the plan's "extend, not break" constraint.
- **Fix:** Function-local imports inside `token_store` / `read_token_pair` / `read_write_token_pair`; RED failure isolated to `tests/test_auth.py` (verified: other suites stayed 37 passed during RED).
- **Files modified:** tests/conftest.py
- **Verification:** During RED, `tests/test_storage.py + test_validation.py + test_parsing.py` passed while `test_auth.py` errored on the missing module.
- **Committed in:** 9b2f6af (task 1 commit)

**2. [Rule 2 - Missing Critical] Scaffold extended past the 8 required areas**
- **Found during:** task 1 (test design)
- **Issue:** The 8 required tests did not pin task-2 contract behaviors the plan text specifies (expiry denial incl. naive-as-UTC, `generate_token` uniqueness/prefix-suffix derivation, `update_last_used` fail-open telemetry, error-class `str` contracts) — leaving them unproven.
- **Fix:** Added 7 tests: `test_expired_token_verifies_none` (past denies, future passes), `test_add_token_generates_unique_values`, `test_update_last_used_never_blocks`, `test_entry_scopes_delegate_to_type`, `test_authentication_error_defaults`, `test_authorization_error_message`, plus blank/whitespace lookup cases folded into `test_unknown_token_verifies_none`.
- **Files modified:** tests/test_auth.py
- **Verification:** All 15 tests green after task 2; suite total 79 passed, 2 skipped.
- **Committed in:** 9b2f6af (scaffold) / proven by 80a8672

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 missing-critical coverage)
**Impact on plan:** Both required for a clean RED phase and full contract proof. No scope creep — no new files, no new dependencies, no behavior beyond the plan's auth.py specification.

## Issues Encountered

None — RED failed for the right reason (missing module), GREEN passed on first run (15/15), no regressions.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for Plan 02 (middleware): `TokenStore.lookup` + `entry.scopes` + both error types are the exact seam `verify_token` / `require_read` / `require_write` build on.
- No blockers. `KB_TOKENS_FILE` override and `~/knowledge-base/.tokens.json` default verified live via smoke test (JSON on disk contains `key_hash` only).

## Self-Check: PASSED

- `src/kb_mcp/auth.py` (204 lines, ≥120) FOUND; `tests/test_auth.py` (175 lines, ≥60) FOUND
- Commits `9b2f6af` and `80a8672` present in `git log`
- Acceptance re-verified post-commit: scope print `['notes:read', 'notes:write']`, transport-grep count 0, full suite 79 passed / 2 skipped

---
*Phase: 03-token-model-middleware*
*Completed: 2026-10-09*
