---
phase: 10-portal-auth-shell-v3-0
plan: "02"
subsystem: ui
tags: [react, vite, supabase-auth, vercel, portal, bff]

# Dependency graph
requires:
  - phase: 10-01
    provides: [BFF GET /api/health, /api/me, /api/admin/ping + Bearer JWT contract]
provides:
  - Vite+React auth shell (signup/login, persistent session header, admin-gated placeholder)
  - Vercel SPA config + deploy docs with service_role-never-on-Vercel warning
  - Live-verified SC-1/SC-2/SC-4 evidence
affects: [phase-11 token self-serve pages, phase-12 KB pages, phase-13 setup pages]

# Tech tracking
tech-stack:
  added: [react@18, react-dom@18, react-router-dom@6, @supabase/supabase-js@2, vite@6, typescript@5.6]
  patterns: [supabase-js default session persistence, Bearer authFetch helper, BFF-message-verbatim denial rendering]

key-files:
  created: [portal/package.json, portal/vite.config.ts, portal/index.html, portal/vercel.json, portal/.env.example, portal/src/main.tsx, portal/src/supabaseClient.ts, portal/src/AuthContext.tsx, portal/src/pages/LoginPage.tsx, portal/src/components/SessionHeader.tsx, portal/src/pages/AdminPlaceholderPage.tsx, portal/src/App.tsx, portal/README.md]
  modified: []

key-decisions:
  - "Hand-wrote Vite scaffold (no create-vite network run) with pinned free-tier stack"
  - "Admin state comes ONLY from BFF /api/admin/ping, never browser claims parsing"
  - "Denial renders the BFF 403 message verbatim with HTTP status, zero user data"

patterns-established:
  - "Portal route guards: unauthenticated redirect /login; auth pages redirect / when logged in"
  - "Key-safety grep (service_role/SUPABASE_DB_URL/x-api-token) must return 0 hits over portal/"

requirements-completed: [PORT-01, PORT-02, PORT-03]

# Metrics
duration: 100min
completed: 2026-10-11
---

# Phase 10 Plan 02: Portal Auth Shell Summary

**Vite+React signup/login with persistent session header and BFF-gated admin placeholder, live-verified against the Plan 10-01 BFF**

## Performance

- **Duration:** 100 min (includes live human-verification session)
- **Started:** 2026-10-11T14:05:00Z
- **Completed:** 2026-10-11T15:46:26Z
- **Tasks:** 3 (2 auto + 1 human-verify checkpoint, approved live)
- **Files modified:** 16

## Accomplishments
- portal/ scaffold (Vite 6 + React 18 + TS + react-router 6 + supabase-js 2) building cleanly with dummy env values — no live backend needed for build
- AuthContext: getSession on mount + onAuthStateChange subscription, email+password signUp/signIn/signOut, authFetch attaching `Authorization: Bearer <access_token>`
- LoginPage (86 lines): signin/signup toggle, verbatim provider errors, logged-in redirect
- SessionHeader: /api/me-driven email + Admin badge, "Checking session…" loading, Login link when logged out
- AdminPlaceholderPage (67 lines): /api/admin/ping-driven loading/denied/granted states, denial renders BFF 403 verbatim + HTTP status
- vercel.json SPA rewrite + README with local/Vercel/backend env docs and SC-3 service_role warning
- Live verification (all observed in browser): signup → login → refresh-persist → non-admin 403 denial → ADMIN_EMAILS bootstrap grant → Admin badge

## task Commits

Each task was committed atomically:

1. **task 1: portal scaffold + auth context** - `efc7047` (feat)
2. **task 2: auth pages + admin denial + Vercel config** - `1c5acd4` (feat)
3. **task 3: human-verify checkpoint** - approved live (SC-1/SC-2/SC-4 all observed)

**Plan metadata:** pending (docs commit below)

## Files Created/Modified
- `portal/package.json` (+ committed `package-lock.json` via `05c3a3e`) - react/supabase/vite deps, `build: tsc --noEmit && vite build`
- `portal/vite.config.ts`, `portal/tsconfig.json` (strict), `portal/index.html` (div#root + /src/main.tsx)
- `portal/.env.example` - exactly the three VITE_ vars, no secrets
- `portal/src/supabaseClient.ts` - createClient with fail-fast missing-env guard, default persist/refresh
- `portal/src/AuthContext.tsx` (82 lines) - session state + Bearer authFetch
- `portal/src/main.tsx` - AuthProvider + BrowserRouter shell
- `portal/src/pages/LoginPage.tsx`, `portal/src/components/SessionHeader.tsx`, `portal/src/pages/AdminPlaceholderPage.tsx`, `portal/src/App.tsx` (routes / /login /admin only, no stub nav)
- `portal/vercel.json`, `portal/README.md`

## Decisions Made
- Hand-written scaffold over `npm create vite` (deterministic file set, no network approval needed); versions pinned per RESEARCH (vite 6, react 18, router 6, supabase-js 2)
- `tsc --noEmit && vite build` as the build gate (tsc + vite per plan)
- Test probe users (`probe*@example.com`, `denial.probe@example.com`) created and deleted via admin API during verification — no residue in Auth

## Deviations from Plan

None - plan executed exactly as written (all acceptance criteria pass: onAuthStateChange/Authorization/Bearer present, key-safety grep 0 hits, min-lines exceeded, build green, vercel.json rewrites, README env docs).

## Issues Encountered
Live-verification environment issues (no code changes required):
- Supabase "Confirm email" was ON (plan assumes D-04 off) → turned OFF in dashboard; stale unconfirmed users deleted and re-registered
- Supabase free-tier email rate limit hit during repeated signups → waited out the hourly window; with confirmation off no further emails send
- `OPTIONS` preflights 400 `Disallowed CORS origin`: server terminal lacked `PORTAL_ORIGINS` (env loaded in wrong terminal). Bypassed decisively with explicit `serve(..., portal_origins='http://localhost:5173')`
- Browser 401s persisted after CORS fix: server terminal also lacked `SUPABASE_URL`/`SUPABASE_ANON_KEY` (fail-closed None). Same loader fix; proven by same-token OK-in-process vs 401-over-HTTP comparison
- Stale browser session (unchanged access_token across re-login) → cleared localStorage auth entry + fresh sign-in
- Test-side: `supabase/` migrations dir shadows the pip package name for naive imports (namespace path) — harmless once supabase-py installed (regular package wins); `uv run` auto-sync dropped pytest from .venv → restored via `uv pip install pytest`

## User Setup Required

None - no external service configuration required (Supabase/Vercel envs are operator deploy steps documented in portal/README.md, verified live locally).

## Next Phase Readiness
- Auth shell complete and live-verified; Phases 11-13 mount token/KB/activity pages onto AuthContext.authFetch + SessionHeader without reworking auth
- Backend BFF (10-01) + portal (10-02) both green; full backend suite re-verified (19/19 portal tests)
- 10-02 key-links verified 2/2 (Bearer fetch pattern, /api/admin/ping denial render)

## Self-Check: PASSED

---
*Phase: 10-portal-auth-shell-v3-0*
*Completed: 2026-10-11*
