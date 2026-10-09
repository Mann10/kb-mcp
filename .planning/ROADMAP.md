# Roadmap: Knowledge Base MCP Server

**Created:** 2026-10-09
**Granularity:** Fine (9 phases)
**Requirements:** 23 v1 requirements mapped

## Phases

- [x] **Phase 1: Storage Foundation** - YAML parsing, file I/O, path validation (2026-10-09)
- [ ] **Phase 2: Git Versioning** - Git integration for note history
- [ ] **Phase 3: Token Model & Middleware** - Token types, storage, verification
- [x] **Phase 4: CLI Token Management** - Full token lifecycle (generate, revoke, list, rotate, TTL) (2026-10-09)
- [ ] **Phase 5: Core Read Tools** - Search, get, list, browse tags
- [ ] **Phase 6: Advanced Filtering** - Tag and date range filtering
- [ ] **Phase 7: Note CRUD Operations** - Create, update, delete notes
- [ ] **Phase 8: Tag Management & Templates** - Tag operations, note templates
- [ ] **Phase 9: Integration & Hardening** - Rate limiting, error handling, audit logging, E2E

## Phase Details

### Phase 1: Storage Foundation
**Goal**: Notes can be reliably stored and retrieved from the filesystem with proper YAML parsing and path safety
**Depends on**: Nothing (first phase)
**Requirements**: STOR-01, STOR-02
**Success Criteria** (what must be TRUE):
  1. A note with YAML frontmatter and markdown body can be written to disk and read back with all metadata intact
  2. YAML frontmatter is parsed correctly with proper type handling (strings stay strings, tags are lists of strings)
  3. Path traversal attempts are rejected — files outside the knowledge base directory cannot be accessed
  4. Malformed YAML frontmatter is detected and reported with a clear error message
**Plans:** 3 plans

Plans:
- [x] 01-01-PLAN.md — Foundation: project scaffolding, error types, pydantic models, YAML frontmatter parsing
- [x] 01-02-PLAN.md — Storage Core: path validation, NoteRepository CRUD, atomic writes
- [x] 01-03-PLAN.md — Integration Tests: full lifecycle, edge cases, security tests

Wave structure:
- Wave 1: 01-01 (no dependencies)
- Wave 2: 01-02 (depends on 01-01)
- Wave 3: 01-03 (depends on 01-01, 01-02)

Cross-cutting constraints:
- All operations must validate path before touching filesystem (D-09, D-10, D-11)
- YAML parsing must use ruamel.yaml for roundtrip preservation (D-01)
- Error messages must include filename and context (D-17, D-18, D-19)

### Phase 2: Git Versioning
**Goal**: Note changes are tracked in git for history and recovery
**Depends on**: Phase 1
**Requirements**: STOR-03
**Success Criteria** (what must be TRUE):
  1. Creating a new note automatically creates a git commit
  2. Updating an existing note creates a new git commit with the changes
  3. Deleting a note creates a git commit removing the file
  4. Git history shows a clear audit trail of all note changes
**Plans:** 2 plans

Plans:
- [x] 02-01-PLAN.md — Git collaborator: dulwich dep + fail-open git_history.py (lazy init, single-file staging, empty-commit guard)
- [x] 02-02-PLAN.md — Storage hooks + real-git tests: write/delete wiring, 8 STOR-03 tests

Wave structure:
- Wave 1: 02-01 (no dependencies)
- Wave 2: 02-02 (depends on 02-01)

### Phase 3: Token Model & Middleware
**Goal**: All tool calls are authenticated and authorized based on token type
**Depends on**: Phase 1
**Requirements**: AUTH-01, AUTH-02
**Success Criteria** (what must be TRUE):
  1. A read-only token can successfully call read tools but is rejected from write tools with a clear error
  2. A read+write token can call both read and write tools
  3. An invalid or missing token is rejected from all tools
  4. Token verification happens on every tool call without requiring per-tool auth code
**Plans:** 2 plans

Plans:
- [x] 03-01-PLAN.md — Token model + store: TokenType/scopes, hashed TokenStore, auth errors, test scaffold
- [x] 03-02-PLAN.md — Middleware + proofs: verify_token, require_read/require_write, SC-1..SC-4 tests

Wave structure:
- Wave 1: 03-01 (no dependencies)
- Wave 2: 03-02 (depends on 03-01)

### Phase 4: CLI Token Management
**Goal**: Administrators can manage the full token lifecycle from the command line
**Depends on**: Phase 3
**Requirements**: AUTH-03, AUTH-04, AUTH-05, AUTH-06, AUTH-07
**Success Criteria** (what must be TRUE):
  1. CLI can generate a new read-only token and a read+write token
  2. CLI can list all active tokens showing type, creation date, and last used (not full token value)
  3. CLI can revoke an existing token, making it immediately invalid
  4. CLI can rotate a token (revoke old, generate new) in a single command
  5. Tokens can be created with a configurable TTL and expire automatically
**Plans:** 2 plans

Plans:
- [x] 04-01-PLAN.md — Store lifecycle: TTL creation, prefix search, soft-revoke, listing, atomic rotate (+ tests/fixtures)
- [x] 04-02-PLAN.md — Typer CLI: generate/list/revoke/rotate, entry point, table+JSON, secrecy proofs

Wave structure:
- Wave 1: 04-01 (no dependencies)
- Wave 2: 04-02 (depends on 04-01)

### Phase 5: Core Read Tools
**Goal**: AI assistants can discover and retrieve notes from the knowledge base
**Depends on**: Phase 3
**Requirements**: READ-01, READ-02, READ-03, READ-04
**Success Criteria** (what must be TRUE):
  1. AI assistant can search notes by keyword and get matching snippets with context
  2. AI assistant can retrieve the full content of a specific note by title
  3. AI assistant can list all notes with metadata (title, tags, date) without loading full content
  4. AI assistant can browse all tags used across notes with counts
**Plans:** 2 plans

Plans:
- [x] 05-01-PLAN.md — Search + get-note tools (READ-01/READ-02, structured returns, require_read gating)
- [ ] 05-02-PLAN.md — List + tags tools (READ-03/READ-04, counts, all-four auth-gate proofs)

Wave structure:
- Wave 1: 05-01 (no dependencies)
- Wave 2: 05-02 (depends on 05-01, shared read_tools.py + test file)

### Phase 6: Advanced Filtering
**Goal**: AI assistants can narrow search results by tag and date range
**Depends on**: Phase 5
**Requirements**: READ-05, READ-06
**Success Criteria** (what must be TRUE):
  1. Search results can be filtered to only include notes with a specific tag
  2. Search results can be filtered to only include notes within a date range
  3. Combined filters (keyword + tag + date) work together correctly
**Plans**: TBD

### Phase 7: Note CRUD Operations
**Goal**: Write-token holders can create, update, and delete notes
**Depends on**: Phase 3, Phase 5
**Requirements**: WRITE-01, WRITE-02, WRITE-03, WRITE-04
**Success Criteria** (what must be TRUE):
  1. Write-token holder can create a new note with title, tags, and markdown content
  2. Write-token holder can update the content of an existing note
  3. Write-token holder can update note metadata (title, tags, dates)
  4. Write-token holder can delete a note by title
  5. All write operations validate input and reject invalid data with clear errors
**Plans**: TBD

### Phase 8: Tag Management & Templates
**Goal**: Write-token holders can manage tags and use templates for common note types
**Depends on**: Phase 7
**Requirements**: WRITE-05, WRITE-06, WRITE-07
**Success Criteria** (what must be TRUE):
  1. Write-token holder can add tags to an existing note
  2. Write-token holder can remove tags from an existing note
  3. Write-token holder can create notes from templates (meeting, book, idea) with pre-populated structure
**Plans**: TBD

### Phase 9: Integration & Hardening
**Goal**: The complete system works end-to-end with proper error handling and operational safety
**Depends on**: All prior phases
**Requirements**: (cross-cutting — no specific requirement IDs)
**Success Criteria** (what must be TRUE):
  1. All tools work together through the MCP protocol with proper authentication
  2. Rate limiting prevents abuse from runaway clients
  3. All write operations are logged for audit purposes
  4. Error messages are clear and actionable (no stack traces to clients)
  5. The server can be started and connected to by an MCP client (Claude Desktop, etc.)
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Storage Foundation | 3/3 | Complete | 2026-10-09 |
| 2. Git Versioning | 2/2 | Complete | 2026-10-09 |
| 3. Token Model & Middleware | 0/2 | Not started | - |
| 4. CLI Token Management | 2/2 | Complete | 2026-10-09 |
| 5. Core Read Tools | 1/2 | In Progress | - |
| 6. Advanced Filtering | 0/5 | Not started | - |
| 7. Note CRUD Operations | 0/8 | Not started | - |
| 8. Tag Management & Templates | 0/6 | Not started | - |
| 9. Integration & Hardening | 0/7 | Not started | - |

## Coverage

| Requirement | Phase |
|-------------|-------|
| AUTH-01 | Phase 3 |
| AUTH-02 | Phase 3 |
| AUTH-03 | Phase 4 |
| AUTH-04 | Phase 4 |
| AUTH-05 | Phase 4 |
| AUTH-06 | Phase 4 |
| AUTH-07 | Phase 4 |
| READ-01 | Phase 5 |
| READ-02 | Phase 5 |
| READ-03 | Phase 5 |
| READ-04 | Phase 5 |
| READ-05 | Phase 6 |
| READ-06 | Phase 6 |
| WRITE-01 | Phase 7 |
| WRITE-02 | Phase 7 |
| WRITE-03 | Phase 7 |
| WRITE-04 | Phase 7 |
| WRITE-05 | Phase 8 |
| WRITE-06 | Phase 8 |
| WRITE-07 | Phase 8 |
| STOR-01 | Phase 1 |
| STOR-02 | Phase 1 |
| STOR-03 | Phase 2 |

**Total:** 23/23 requirements mapped (100%)
