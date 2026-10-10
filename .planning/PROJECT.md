# Knowledge Base MCP Server

## What This Is

An MCP server that provides AI assistants with read access to a personal knowledge base of YAML-formatted notes. The server enforces strict permissions: read-only access for the owner's team, and read+write access only for explicitly authorized individuals.

## Core Value

Enable AI assistants to search and read personal notes while ensuring only authorized users can modify the knowledge base.

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

- [ ] AI assistants can search notes by keyword
- [ ] AI assistants can retrieve full note content
- [ ] AI assistants can list all available notes
- [ ] AI assistants can browse tags
- [ ] Write-token holders can create new notes
- [ ] Write-token holders can update existing notes
- [ ] Write-token holders can delete notes
- [ ] Write-token holders can manage tags
- [ ] Separate read-only and read+write tokens

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
*Last updated: 2026-10-10 after Phase 8 completion*
