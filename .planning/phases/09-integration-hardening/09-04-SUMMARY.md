---
phase: 09-integration-hardening
plan: 04
subsystem: testing
tags: [e2e, streamable-http, fastmcp-client, subprocess, hermetic]

# Dependency graph
requires:
  - phase: 09-integration-hardening (09-03)
    provides: [header-auth transport with verify→rate→invoke pipeline, locked denial strings, traceback-free error mapping]
provides:
  - Booted-server + real-client E2E proofs for SC-1..SC-4 (tests/test_server_e2e.py)
  - Transport-half proof of SC-5 (kb-mcp serve subprocess serves real protocol clients)
affects: [09-05 live Claude Desktop verification]

# Tech tracking
tech-stack:
  added: []
  patterns: [module-scoped booted-server fixture with tmp env isolation, per-call Client sessions with StreamableHttpTransport headers, serialized-payload traceback blanket assertion]

key-files:
  created: [tests/test_server_e2e.py]
  modified: []

key-decisions:
  - "FastMCP Client with StreamableHttpTransport(url, headers) per call, since Client itself takes no headers param in fastmcp 4.1.0"
  - "Readiness via TCP connect poll (not tools/list), so a boot failure fails loudly before any protocol assertion"

patterns-established:
  - "E2E isolation: free port per run, tmp NOTES_DIR/store/audit via env, dedicated flood token, terminate+wait in finally"
  - "Every response assertion serializes the full payload first and asserts Traceback absence (SC-4 blanket rule)"

requirements-completed: []

# Metrics
duration: 3min
completed: 2026-10-10
---

# Phase 9 Plan 04: Booted-Server E2E Proofs Summary

**Real `kb-mcp serve` subprocess driven by streamable-http MCP clients proving SC-1 reads/writes, SC-2 rate trip, SC-3 audit lines, and SC-4 traceback-free errors — 7 E2E tests green in ~5 s**

## Performance

- **Duration:** 3 min
- **Started:** 2026-10-10T13:14:45+05:30
- **Completed:** 2026-10-10T13:17:00+05:30
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- Module-scoped `live_server` fixture boots the real D-04 entry (`kb-mcp serve --port <free> --notes-dir <tmp>`) with seeded `alpha.md`/`beta.md` notes, READ + READ_WRITE + flood tokens in a tmp store, and `NOTES_DIR`/`KB_TOKENS_FILE`/`KB_AUDIT_FILE`/`KB_HOST` env pinned to tmp dirs; TCP readiness poll up to 15 s, `terminate+wait` in `finally`, loud failure on early exit (no in-process downgrade)
- `call_tool` helper uses `StreamableHttpTransport(url, headers={"x-api-token": raw})` per call (Client takes no headers param in fastmcp 4.1.0) and normalizes dict / structured_content / content-block payloads; smoke tests prove all 10 tools listed and unauthenticated calls denied with `Invalid or missing token.` over the real protocol
- SC-1..SC-4 proven over protocol: `wombat-signal` search hits `alpha`, Beta read-back, 2-note list, `e2e` tag; write-token create + add_tags with `user=e2e-writer` / `tool=create_note` / `file=e2e-gamma` audit lines; read-token-on-write denied with the locked `Write access required...` string; rate trip fires on the dedicated flood token within 35 calls with `Rate limit` + `60`; not-found and empty-title errors structured with no `Traceback` in any serialized response
- Full suite 250 passed + 2 skipped (was 243 + 2, no regressions); E2E file runs in ~5 s (< 120 s budget); no reference to the real home knowledge-base outside one isolation docstring; snippet URL `http://localhost:8000/mcp` matches the served `/mcp` path convention for 09-05

## task Commits

Each task was committed atomically:

1. **task 1: Build booted-server E2E harness with seeded notes and tokens** - `7d0d5ec` (feat)
2. **task 2: Prove SC-1..SC-4 over the real protocol** - `706eeeb` (test)

**Plan metadata:** `docs(09-04)` commit (STATE.md + ROADMAP.md + this SUMMARY)

## Files Created/Modified

- `tests/test_server_e2e.py` (created) - `live_server` fixture, `call_tool`/`list_tool_names` helpers, 2 smoke tests + 5 SC proof tests

## Decisions Made

- FastMCP `Client` constructor takes no `headers` argument in 4.1.0 (verified via `help()`), so each protocol call builds `StreamableHttpTransport(url, headers={...})` and opens a short `async with Client(transport)` session — executor's-discretion branch committed, httpx raw-JSON-RPC fallback deleted per plan instruction.
- Readiness uses a TCP-connect poll rather than `tools/list`, so a dead server fails loudly at fixture setup instead of surfacing as a confusing protocol error in the first test.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 09-05 (live Claude Desktop connect): transport half of SC-5 proven — booted `kb-mcp serve` answers real MCP clients at `/mcp` with header auth; snippet points at `http://localhost:8000/mcp`.
- Note for 09-05: E2E seeds are tmp-only; live verification will need a real NOTES_DIR + real tokens per the snippet.
- No blockers.

---
*Phase: 09-integration-hardening*
*Completed: 2026-10-10*

## Self-Check: PASSED

- FOUND: tests/test_server_e2e.py (7 tests, all green in 5.28 s)
- FOUND: 7d0d5ec, 706eeeb (`git log --oneline` confirms both on master)
- All plan-level `<verification>` commands re-run green (e2e 7 passed < 120 s, full suite 250 passed + 2 skipped, home/knowledge-base grep shows only the isolation docstring, snippet URL matches /mcp convention)
