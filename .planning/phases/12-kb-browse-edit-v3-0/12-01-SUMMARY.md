---
phase: 12-kb-browse-edit-v3-0
plan: "01"
subsystem: api
tags: [fastmcp, starlette, bff, kb-read, jwt-gate]

# Dependency graph
requires:
  - phase: 11-token-self-serve-admin-v3-0
    provides: portal_auth require_user gate, BFF custom_route + CORS pattern, TokenStore with username = login email
  - phase: 10-portal-auth-shell-v3-0
    provides: RequireAuth shell, authFetch Bearer-JWT pattern, PORTAL_INVALID_MESSAGE contract
provides:
  - D-13 write-access choke point has_write_access() imported by read can_write and all write routes
  - Six require_user-gated KB read BFF endpoints with v1 byte-identical messages
  - Level 1 read contract tests plus Level 2 parity proofs green
affects: [12-02 write BFF, 12-03 browse UI, kb-browse-edit-v3-0]

# Tech tracking
tech-stack:
  added: []
  patterns: [BFF replicates gated-tool semantics over per-call repo dispatch instead of calling token-gated tools, module-style portal_auth import for monkeypatching, explicit OPTIONS per route]

key-files:
  created: [src/kb_mcp/portal_kb_gate.py, src/kb_mcp/portal_kb_read_routes.py, tests/test_portal_kb_read.py]
  modified: [src/kb_mcp/server.py]

key-decisions:
  - "BFF result rows use stem key (not filename) per frozen BFF contract in 12-03 interfaces"
  - "Gate compares token type dash/underscore-tolerant (read_write and read-write both grant)"
  - "Invalid-date search returns HTTP 200 with verbatim v1 message (not 400)"

patterns-established:
  - "BFF test isolation: monkeypatch backend dispatch plus route-module reference, real filesystem NoteRepository on tmp_path"
  - "Parity proof: compare BFF message against gated read_tools output with real token plus store"

requirements-completed: ["BROW-01", "BROW-02", "BROW-03"]

# Metrics
duration: 25min
completed: 2026-10-12
---

# Phase 12 Plan 01: KB Read BFF Summary

**Six require_user-gated KB read endpoints over HTTP with v1-ranked search, D-13 write-gate helper, and 14 green contract tests**

## Performance

- **Duration:** 25 min
- **Started:** 2026-10-12T06:00:00Z
- **Completed:** 2026-10-12T06:25:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- D-13 gate helper `has_write_access()` fail-closed on empty email, store errors, revoked/expired/read-only tokens
- Six read routes (search/list/get/tags/templates/can_write) with v1 byte-identical ranking, snippets, filters, and messages
- Server mount beside existing portal route imports; module import clean
- 14 contract + parity tests green (rank order, byte-identical empty state, normalized tag, inclusive dates, limit clamp, 401, can_write leak check)

## task Commits

Each task was committed atomically:

1. **task 1: write D-13 gate helper portal_kb_gate.py** - `8deb120` (feat)
2. **task 2: write six KB read BFF routes + mount** - `d982db6` (feat)
3. **task 3: read contract tests + parity proofs** - `ab03c2d` (test)

**Plan metadata:** pending (docs: complete plan — commit_docs disabled, SUMMARY committed at phase end)

## Files Created/Modified

- `src/kb_mcp/portal_kb_gate.py` - D-13 write-access choke point `has_write_access()`
- `src/kb_mcp/portal_kb_read_routes.py` - Six KB read BFF routes with v1 parity core
- `src/kb_mcp/server.py` - Mount `portal_kb_read_routes` beside portal route imports
- `tests/test_portal_kb_read.py` - 14 Level 1 + Level 2 read tests

## Decisions Made

- BFF result rows use the `stem` key (not v1 `filename`) per the frozen BFF contract in 12-03 interfaces; messages stay byte-identical
- Gate type comparison is dash/underscore-tolerant so `read_write` and `read-write` both grant (auth.py stores `read_write`)
- Invalid-date search returns HTTP 200 with the verbatim v1 message, matching read_tools behavior rather than a 400

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 12-02 (write BFF imports `has_write_access` from `portal_kb_gate`; read routes prove the mount + auth pattern)
- No blockers or concerns

## Self-Check: PASSED

- Key files exist on disk: `src/kb_mcp/portal_kb_gate.py`, `src/kb_mcp/portal_kb_read_routes.py`, `tests/test_portal_kb_read.py`
- `git log --oneline --all --grep="12-01"` returns 3 commits (8deb120, d982db6, ab03c2d)
- All task acceptance criteria re-verified PASS (six route paths, module-style portal_auth import, server mount, 14 test_ functions, can_write + 401 coverage)
- Plan verification green: `pytest tests/test_portal_kb_read.py -x -q` → 14 passed; `import kb_mcp.portal_kb_read_routes, kb_mcp.server` clean

---
*Phase: 12-kb-browse-edit-v3-0*
*Completed: 2026-10-12*
