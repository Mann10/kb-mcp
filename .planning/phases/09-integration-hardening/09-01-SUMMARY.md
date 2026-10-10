---
phase: 09-integration-hardening
plan: 01
subsystem: api
tags: [fastmcp, streamable-http, typer, mcp-server, fail-fast]

# Dependency graph
requires:
  - phase: 05-core-read-tools
    provides: [gated read tools with require_read + structured dict returns]
  - phase: 07-note-crud-operations
    provides: [gated create/update/delete tools with require_write]
  - phase: 08-tag-management-templates
    provides: [gated add_tags/remove_tags/create_from_template tools]
provides:
  - FastMCP KnowledgeBase app with 10 registered tool wrappers (D-08 skeleton)
  - `kb-mcp serve` entry point on streamable-http 0.0.0.0:8000 (D-01/D-02/D-04)
  - Fail-fast NOTES_DIR startup guard (D-06)
  - Verified Claude Desktop client snippet (D-05)
affects: [09-02 rate limiting + audit, 09-03 transport auth + error mapping, 09-04 E2E proofs]

# Tech tracking
tech-stack:
  added: [fastmcp>=4,<5 (runtime resolved 4.1.0)]
  patterns: [thin annotated MCP wrappers delegating with token+_store kwargs, lazy fastmcp import in CLI]

key-files:
  created: [src/kb_mcp/server.py, claude_desktop_config.example.json]
  modified: [pyproject.toml, src/kb_mcp/cli.py]

key-decisions:
  - "CLI serve resolves KB_HOST/KB_PORT/NOTES_DIR at call time with static typer defaults (env wins without import-time coupling)"
  - "serve() injects a shared NoteRepository via configure_default_repo after the fail-fast check, so --notes-dir works without env mutation"
  - "Snippet uses the runtime-confirmed /mcp streamable-http path"

patterns-established:
  - "Wrapper delegation: clean annotated signatures call gated tools with token=raw, _store=store; transport auth stub fails closed via get_request_token()"
  - "Fail-fast startup: ensure_notes_dir raises SystemExit mentioning NOTES_DIR; no silent auto-create anywhere in the serve path"

requirements-completed: []

# Metrics
duration: ~25min
completed: 2026-10-10
---

# Phase 9 Plan 01: Server Foundation Summary

**FastMCP KnowledgeBase server with 10 clean-schema tool wrappers on streamable-http 0.0.0.0:8000, fail-fast NOTES_DIR startup, `kb-mcp serve` entry, and a boot-verified Claude Desktop snippet**

## Performance

- **Duration:** ~25 min (wall-clock, approximate)
- **Completed:** 2026-10-10T07:30:14Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- `fastmcp>=4,<5` dependency declared; `kb-mcp` script entry installed alongside `kb-mcp-tokens`; `kb-mcp serve --help` shows host/port/notes-dir options
- `src/kb_mcp/server.py` created: FastMCP app, `resolve_notes_dir` (explicit > NOTES_DIR > ~/knowledge-base/notes), `ensure_notes_dir` fail-fast guard, 10 `@mcp.tool()` wrappers, `serve()` locked to `transport="streamable-http"`, `get_request_token()` stub failing closed until Plan 09-03
- Fail-fast proven inline (precedence + SystemExit on missing dir) and through the real CLI (`kb-mcp serve` exits 1 with NOTES_DIR message on missing dir)
- Server booted on a test port: FastMCP banner confirms `streamable-http on http://0.0.0.0:8023/mcp`, locking the `/mcp` path used in the snippet
- `claude_desktop_config.example.json` shipped as valid JSON pointing at `http://localhost:8000/mcp` with an `x-api-token` header note and no secrets
- Full suite green: 224 passed, 2 skipped; `middleware.py` untouched

## task Commits

Each task was committed atomically:

1. **task 1: Add fastmcp dependency and kb-mcp serve entry point** - `eedb710` (feat)
2. **task 2: Create server.py with config, fail-fast, and 10 tool wrappers** - `73f9bae` (feat)
3. **task 3: Fail-fast proofs plus Claude Desktop snippet** - `c9a04a5` (feat)

## Files Created/Modified

- `src/kb_mcp/server.py` (created) - FastMCP app, env config, fail-fast startup, 10 registered tool wrappers, serve entry
- `claude_desktop_config.example.json` (created) - Claude Desktop client config snippet (D-05)
- `pyproject.toml` (modified) - `fastmcp>=4,<5` dependency + `kb-mcp` script entry
- `src/kb_mcp/cli.py` (modified) - Lazy `serve` command honoring KB_HOST/KB_PORT/NOTES_DIR

## Decisions Made

- CLI serve resolves KB_HOST/KB_PORT/NOTES_DIR at call time with static typer defaults (env wins without import-time coupling) — keeps `kb-mcp-tokens` free of fastmcp imports and honors D-02/D-03 defaults.
- `serve()` injects a shared `NoteRepository` via `configure_default_repo` after the fail-fast check, so `--notes-dir` works without env mutation; `TokenStore.load()` keeps honoring `KB_TOKENS_FILE` (D-03).
- Snippet uses the runtime-confirmed `/mcp` streamable-http path (observed in the booted server banner).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Probe scripts spawning `kb-mcp serve` as a child process hung the shell tool on pipe handling (two attempts, file-redirect variant included). Resolved by booting via `Start-Process` with log-file redirects, confirming the `/mcp` path from the server banner, then stopping the process. No stray server processes remain. Full E2E with real protocol calls stays in Plan 09-04 scope.
- Runtime resolved `fastmcp` 4.1.0 (within the `>=4,<5` pin) rather than the researched 4.0.11 — API used (`FastMCP`, `@mcp.tool()`, `mcp.run(transport=...)`) is unchanged.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 09-02 (rate limit + audit modules) and 09-03 (transport auth wiring `get_request_token()` + error mapping hook into the wrapper skeleton).
- No blockers. `middleware.py` semantics untouched per D-08.

---
*Phase: 09-integration-hardening*
*Completed: 2026-10-10*

## Self-Check: PASSED

- FOUND: src/kb_mcp/server.py
- FOUND: claude_desktop_config.example.json
- FOUND: eedb710, 73f9bae, c9a04a5 (`git log --oneline` confirms all three on master)
- All plan-level `<verification>` commands re-run green (serve help, import-clean, 10 wrappers, fail-fast exit 1, snippet JSON, pytest 224 passed)
