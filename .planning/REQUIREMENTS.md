# Requirements: Knowledge Base MCP Server — v3.0 UIF Token Portal

**Defined:** 2026-10-11
**Core Value:** Enable AI assistants to search and read personal notes while ensuring only authorized users can modify the knowledge base.

## v3.0 Requirements

Token portal + control panel (separate frontend). Every requirement maps to the v3 roadmap (phases 10+).

### Portal Auth

- [x] **PORT-01**: User can sign up / log in with email via the UI
- [x] **PORT-02**: User session persists across browser refresh in the UI
- [x] **PORT-03**: Admin role gates all approve/mint/revoke and settings actions in the UI

### Token Self-Serve & Admin

- [ ] **TOK-01**: Logged-in user can self-serve a new read-only token from the UI
- [ ] **TOK-02**: Logged-in user can view their own tokens (masked value, type, created, expiry, status)
- [ ] **TOK-03**: Logged-in user can request a write-token upgrade from the UI
- [ ] **TOK-04**: Admin can approve or deny write-token requests from a queue in the UI
- [ ] **TOK-05**: Admin can directly mint a read or read-write token for any user from the UI
- [ ] **TOK-06**: Admin can revoke, rotate, and list all tokens from the UI (parity with CLI lifecycle)

### KB Browsing

- [ ] **BROW-01**: User can search notes by keyword from the UI with snippets
- [ ] **BROW-02**: User can read full note content from the UI
- [ ] **BROW-03**: User can list notes with metadata and browse tags from the UI

### KB Editing

- [ ] **EDIT-01**: Write-authorized user can create a note (incl. from meeting/book/idea template) from the UI
- [ ] **EDIT-02**: Write-authorized user can update note content and metadata from the UI
- [ ] **EDIT-03**: Write-authorized user can delete a note from the UI
- [ ] **EDIT-04**: Write-authorized user can add/remove tags from the UI

### Client Setup

- [ ] **SETUP-01**: User gets a personalized Claude Desktop config snippet (Horizon URL + headers + their token) from the UI
- [ ] **SETUP-02**: User gets step-by-step connect instructions (mcp-remote, Horizon key, restart) from the UI

### Activity

- [ ] **ACT-01**: Admin can view the audit log (who called what, when) from the UI
- [ ] **ACT-02**: Admin can view note revision history (actor, action, snapshot) from the UI
- [ ] **ACT-03**: Admin can view per-token usage (last used, call counts) from the UI

### Settings

- [ ] **CONF-01**: Admin can manage token defaults (default TTL, default type) from the UI
- [ ] **CONF-02**: Admin can manage note templates (meeting/book/idea skeletons + default tags) from the UI
- [ ] **CONF-03**: Admin can manage client setup snippets (Horizon URL, header format, instructions text) from the UI

## Future Requirements

Deferred beyond v3.0. Tracked but not in current roadmap.

### UIF Next

- **UIF-01**: Bulk import of local markdown notes into Supabase from the UI
- **UIF-02**: Per-note ACLs (share individual notes with specific users)
- **UIF-03**: In-UI diff view of revision snapshots with restore
- **UIF-04**: Email notifications on token request / approval

## Out of Scope

| Feature | Reason |
|---------|--------|
| Infra/env editing from UI (Horizon env vars, Supabase connection strings) | Secrets must stay in Horizon dashboard; UI never touches infra — decided in brainstorming |
| Open (login-free) token minting | Abuse risk; login gate + admin approval preserves single-writer trust model |
| Real-time collaboration | Single-user write model unchanged from v1 |
| Multi-tenancy / RLS policies | Single-tenant personal KB; service_role bypass stands |
| Native mobile app | Web UI first; mobile later if ever |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PORT-01 | Phase 10 | Complete |
| PORT-02 | Phase 10 | Complete |
| PORT-03 | Phase 10 | Complete |
| TOK-01 | Phase 11 | Pending |
| TOK-02 | Phase 11 | Pending |
| TOK-03 | Phase 11 | Pending |
| TOK-04 | Phase 11 | Pending |
| TOK-05 | Phase 11 | Pending |
| TOK-06 | Phase 11 | Pending |
| BROW-01 | Phase 12 | Pending |
| BROW-02 | Phase 12 | Pending |
| BROW-03 | Phase 12 | Pending |
| EDIT-01 | Phase 12 | Pending |
| EDIT-02 | Phase 12 | Pending |
| EDIT-03 | Phase 12 | Pending |
| EDIT-04 | Phase 12 | Pending |
| SETUP-01 | Phase 13 | Pending |
| SETUP-02 | Phase 13 | Pending |
| ACT-01 | Phase 13 | Pending |
| ACT-02 | Phase 13 | Pending |
| ACT-03 | Phase 13 | Pending |
| CONF-01 | Phase 13 | Pending |
| CONF-02 | Phase 13 | Pending |
| CONF-03 | Phase 13 | Pending |

**Coverage:**
- v3.0 requirements: 24 total
- Mapped to phases: 24
- Unmapped: 0 ✓

## Prior Milestones

- **v1.0** (complete): 23 requirements (AUTH-01..07, READ-01..06, WRITE-01..07, STOR-01..03) — local FastMCP server, CLI tokens, read/write tools, git versioning, hardening.
- **v2** (deployed per owner 2026-10-11): stateless Supabase backend + Horizon live deploy (`HORIZON_DEPLOY.md`, `supabase/migrations/`, `horizon_entry.py`).

---
*Requirements defined: 2026-10-11*
*Last updated: 2026-10-11 after v3.0 scoping*
