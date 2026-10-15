# Knowledge Base MCP Server

## What This Is

An MCP server that provides AI assistants with read access to a personal knowledge base of YAML-formatted notes. The server enforces strict permissions: read-only access for the owner's team, and read+write access only for explicitly authorized individuals.

## Core Value

Enable AI assistants to search and read personal notes while ensuring only authorized users can modify the knowledge base.

## Current Milestone: v3.0 UIF Token Portal

**Goal:** A separate frontend UI where logged-in users self-serve read-only tokens and browse the KB, while the admin approves write-token upgrades — plus client setup guide and KB/app settings management.

**Target features:**
- Login-gated token portal with read-only token self-serve
- Write-token request + admin approve/deny flow (plus direct admin mint)
- KB browsing/search and in-UI note + tag editing
- One-click client setup guide (Claude Desktop config with embedded token)
- Activity views (audit log, revision history, token usage)
- KB/app settings management from UI (TTL defaults, templates, client snippets)

## Requirements

### Validated

- [x] YAML frontmatter parsing with type validation (Phase 1)
- [x] Note storage on disk with filesystem as source of truth (Phase 1)
- [x] Path validation and traversal prevention (Phase 1)
- [x] Atomic writes for note operations (Phase 1)
- [x] Git versioning of note changes with fail-open commits (Phase 2)
- [x] Separate read-only and read+write tokens (Phase 3: TokenType scopes, hash-only TokenStore)
- [x] Token verification on every tool call via decorators (Phase 3: middleware verify_token/require_read/require_write)
- [x] CLI tool for token generation and revocation (Phase 4: typer generate/list/revoke/rotate, TTL, kb-mcp-tokens entry point)
- [x] Write-token holders can create new notes with structured validation (Phase 7: create_note with slugify + exists-reject)
- [x] Write-token holders can update existing notes incl. title-rename with single-commit atomicity (Phase 7: update_note + commit_note_rename)
- [x] Write-token holders can delete notes with structured not-found (Phase 7: delete_note)
- [x] Write-token holders can add tags to existing notes with idempotent merge (Phase 8: add_tags)
- [x] Write-token holders can remove tags from existing notes with idempotent merge (Phase 8: remove_tags)
- [x] Write-token holders can create notes from templates meeting/book/idea (Phase 8: create_from_template)

### Active

- [x] Logged-in users can self-serve read-only tokens from the UI (Validated in Phase 11: token-self-serve-admin — mint + masked list + cap/TTL)
- [x] Users can request write-token upgrades; admin can approve/deny or mint directly (Validated in Phase 11: queue + approve-mints-fresh + direct mint)
- [ ] Users can browse/search notes and tags from the UI
- [ ] Write-authorized users can create/edit notes and manage tags from the UI
- [ ] Users get a copy-paste client setup guide (Claude Desktop + Horizon + x-api-token)
- [ ] Admin can view activity (audit log, revision history, token usage) from the UI
- [ ] Admin can manage KB/app settings from the UI (TTL defaults, templates, snippets)

### Out of Scope

- Real-time collaboration — single-user write model
- Web UI for browsing — MCP tools are the interface
- Full-text search engine — simple keyword matching is sufficient

## Context

- Existing reference implementation at `C:\personal\CD\MCP` (FastMCP with markdown notes, token auth, rate limiting)
- Notes use YAML frontmatter (title, tags, created date) + markdown body format
- Token management via CLI tool (generate, revoke, list)
- Learning reference: https://github.com/CatalinStefan/fastmcp-course
- Target users: owner + team members who use AI assistants (Claude, ChatGPT, etc.)
- v2 milestone: stateless Supabase backend + Horizon deployment — server live at `https://kb-mcp.fastmcp.app/mcp` (see `HORIZON_DEPLOY.md`); CLI token ops work against Supabase via `KB_BACKEND=supabase`
- v3 milestone: separate frontend UIF — login required (provider TBD during planning, Supabase Auth leading candidate), request+approve write-token flow, KB/app settings only (no infra/env editing)
- Phase 10 complete (2026-10-11): portal auth shell — Supabase Auth login/session, BFF JWT gates, admin denial state, RequireAuth / → /login guard. Foundation for self-serve tokens (Phase 11).

## Constraints

- **Tech stack**: Python + FastMCP — proven in reference implementation
- **Note format**: YAML frontmatter + markdown body — matches existing notes
- **Auth**: Token-based with separate read/write permissions — required for team access
- **Scope**: Personal knowledge base, not a multi-tenant system

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Separate read/write tokens | Team needs read-only access while only owner (or select individuals) can modify | — Pending |
| YAML frontmatter + markdown body | Matches existing notes format, human-readable, easy to parse | — Pending |
| CLI token management | Consistent with reference implementation, simple to automate | — Pending |
| MCP write tools for updates | Team members can contribute to KB without direct file access | — Pending |
| Separate frontend for UIF (v3.0) | Token portal + KB ops don't belong in MCP protocol; independent deploy, independent auth | — Pending |
| Login-gated self-serve reads, request+approve writes (v3.0) | Open token mint invites abuse; login + admin gate keeps single-writer trust model | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-10-12 after Phase 11 token-self-serve-admin*
