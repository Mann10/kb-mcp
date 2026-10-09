---
phase: 04-cli-token-management
plan: 01
subsystem: auth
tags: [tokens, tokenstore, ttl, revoke, rotate, prefix-search, pytest]

# Dependency graph
requires:
  - phase: 03-token-model-middleware
    provides: Hashed TokenStore with lookup/save/load, revoked_at/expires_at fail-closed enforcement
provides:
  - TokenStore lifecycle API (expires_at creation, find_by_prefix, revoke_by_prefix, list_entries, token_status, rotate_by_prefix)
  - Prefix fixtures (shared_prefix_store, revoked_entry_store, expired_entry_store) for CLI tests
  - Six lifecycle tests proving revoke/rotate/TTL/prefix/list behavior
affects: [04-cli-token-management plan 02 (Typer CLI), phase 09 audit/hardening]

# Tech tracking
tech-stack:
  added: []
  patterns: [soft-revoke with cardinality gate, prefix-only matching, verbatim TTL carryover on rotate]

key-files:
  created: []
  modified: [src/kb_mcp/auth.py, tests/test_auth.py, tests/conftest.py]

key-decisions:
  - "TTL stored verbatim at write time; lookup/list parse and deny on unparsable (fail-closed)"
  - "Prefix matching on key_prefix only with empty/whitespace returning [] (no match-all dump)"
  - "Rotation carries username+type+TTL verbatim with no new_type parameter (no privilege escalation)"
  - "Shared-prefix fixture uses distinct 8-char prefixes so full prefixes disambiguate"

patterns-established:
  - "Cardinality gate before mutation: 0/2+ matches raise KeyError with no save, proven by len(store) assertions"
  - "Status helper token_status() as single classifier for CLI rendering (revoked > expired > active)"

requirements-completed: [AUTH-04, AUTH-06, AUTH-07]

# Metrics
duration: 2min
completed: 2026-10-09
---

# Phase 04 Plan 01: Store Lifecycle Summary

**TokenStore gains TTL creation, prefix search, soft-revoke, filtered listing, and atomic rotation with six lifecycle tests green**

## Performance

- **Duration:** 2 min
- **Started:** 2026-10-09T16:49:00Z
- **Completed:** 2026-10-09T16:50:40Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `add_token` accepts optional `expires_at` (None default = never-expires) without breaking existing 3-arg calls
- `find_by_prefix` / `revoke_by_prefix` / `list_entries` / `token_status` implement the fat-store API Plan 02's CLI calls
- `rotate_by_prefix` atomically revokes old and mints new carrying username+type+TTL
- Six new lifecycle tests prove revoke-keeps-entry, zero/ambiguous gates mutate nothing, rotate identity, TTL enforcement, never-expires
- Full suite green: 94 passed, 2 skipped (was 88 passed before plan)

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend TokenStore with TTL creation, prefix search, soft-revoke, and listing** - `b42f73e` (feat)
2. **Task 2: Atomic rotate plus lifecycle tests and prefix fixtures** - `dad4c2f` (feat)

**Plan metadata:** pending final docs commit (see below)

## Files Created/Modified

- `src/kb_mcp/auth.py` - Added `expires_at` kwarg to `add_token`, `find_by_prefix`, `revoke_by_prefix` (D-08 gate), `list_entries` (active filtering), `token_status` helper, `rotate_by_prefix` (identity carryover); lookup/save/load untouched
- `tests/test_auth.py` - Six lifecycle tests (revoke-denies-but-keeps, no-match gate, ambiguous gate, rotate identity, TTL enforced, no-TTL active)
- `tests/conftest.py` - Three fixtures: `shared_prefix_store` (colliding 4-char pair), `revoked_entry_store` (real revoke path), `expired_entry_store` (past ISO expiry)

## Decisions Made

- TTL stored verbatim at write time; parse/deny happens in lookup/list (fail-closed, unparsable counts as expired) — matches plan's "no parsing at write time" instruction and reuses `_parse_expiry` naive→UTC normalization
- Prefix matching restricted to `key_prefix.startswith(prefix)` only; empty/whitespace returns `[]` — prevents match-all dump (T-04-03)
- Rotation has no `new_type` parameter; new entry copies `old.token_type` verbatim — prevents privilege escalation (T-04-02)
- Shared-prefix fixture uses `test-aaaa-shared-0001` / `test-bbbb-shared-0002` (distinct 8-char prefixes sharing `test`) rather than the plan's verbatim example raws (which would collide on all 8 chars and could never disambiguate) — preserves the plan's stated intent that full prefixes disambiguate while keeping `find_by_prefix("test")` ambiguous

## Deviations from Plan

None - plan executed exactly as written.

The fixture raw-value choice above is an instantiation of the plan's `e.g.` example, not a deviation: acceptance criteria only require fixture names and ambiguous behavior, both satisfied.

## Issues Encountered

- Plan's manual smoke command passes `store_path` as `str` (`TokenStore(store_path='/tmp/t.json')`) but `TokenStore.__init__` calls `self.store_path.parent`, which fails on `str`. Pre-existing behavior, out of scope (Rule boundary: not caused by this plan). Verified the same smoke with `Path('/tmp/t.json')` prints `True True`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 04-02 (Typer CLI): store API complete with prefix fixtures available for CLI tests
- `lookup()` enforcement unchanged — revoke/rotate/TTL get denial for free via existing `revoked_at`/`expires_at` checks
- No blockers

---
*Phase: 04-cli-token-management*
*Completed: 2026-10-09*

## Self-Check: PASSED
- FOUND: src/kb_mcp/auth.py (def revoke_by_prefix, rotate_by_prefix, token_status)
- FOUND: tests/test_auth.py (6 new lifecycle tests, 21 passed)
- FOUND: tests/conftest.py (shared_prefix_store, revoked_entry_store, expired_entry_store)
- FOUND: b42f73e feat(04-01) extend TokenStore
- FOUND: dad4c2f feat(04-01) rotate plus tests
- Verification: uv run pytest tests/test_auth.py -q → 21 passed; uv run pytest tests/ -q → 94 passed, 2 skipped
