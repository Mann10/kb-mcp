# Requirements: Knowledge Base MCP Server

**Defined:** 2026-10-09
**Core Value:** Enable AI assistants to search and read personal notes while ensuring only authorized users can modify the knowledge base.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Authentication

- [ ] **AUTH-01**: Separate read-only and read+write tokens enforced on all tools
- [ ] **AUTH-02**: Token verification middleware validates token on every tool call
- [x] **AUTH-03**: CLI tool generates new tokens with specified permission level
- [x] **AUTH-04**: CLI tool revokes existing tokens
- [x] **AUTH-05**: CLI tool lists all active tokens
- [x] **AUTH-06**: Token rotation revokes old token and generates new one in single step
- [x] **AUTH-07**: Tokens support configurable TTL with expiration enforcement

### Read Tools

- [x] **READ-01**: Search notes by keyword returning matching snippets
- [x] **READ-02**: Get full note content by title
- [x] **READ-03**: List all notes with metadata only (title, tags, date)
- [x] **READ-04**: Browse all tags across notes
- [x] **READ-05**: Filter search results by tag
- [x] **READ-06**: Filter search results by date range

### Write Tools

- [x] **WRITE-01**: Create new note with YAML frontmatter and markdown body
- [ ] **WRITE-02**: Update existing note content
- [ ] **WRITE-03**: Update existing note metadata (title, tags, dates)
- [x] **WRITE-04**: Delete note by title
- [ ] **WRITE-05**: Add tags to a note
- [ ] **WRITE-06**: Remove tags from a note
- [ ] **WRITE-07**: Note templates for common note types (meeting, book, idea)

### Storage

- [x] **STOR-01**: Parse and validate YAML frontmatter metadata
- [x] **STOR-02**: Store notes as markdown files on disk (no database)
- [x] **STOR-03**: Git versioning integration for note history

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Advanced Features

- **ADV-01**: Note backlinks / related notes discovery
- **ADV-02**: Bulk import from markdown files
- **ADV-03**: SQLite FTS5 full-text search index
- **ADV-04**: Web UI for browsing notes
- **ADV-05**: Multi-tenant architecture

## Out of Scope

| Feature | Reason |
|---------|--------|
| Real-time collaboration | Single-user write model, no conflict resolution needed |
| Web UI for editing | MCP tools are the interface |
| External embedding services | Adds complexity, not core value |
| Database backend | File-based storage sufficient for personal KB scale |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTH-01 | Phase 3 | Pending |
| AUTH-02 | Phase 3 | Pending |
| AUTH-03 | Phase 4 | Complete (04-02) |
| AUTH-04 | Phase 4 | Complete (04-02) |
| AUTH-05 | Phase 4 | Complete (04-02) |
| AUTH-06 | Phase 4 | Complete (04-02) |
| AUTH-07 | Phase 4 | Complete (04-02) |
| READ-01 | Phase 5 | Complete (05-01) |
| READ-02 | Phase 5 | Complete (05-01) |
| READ-03 | Phase 5 | Complete (05-02) |
| READ-04 | Phase 5 | Complete (05-02) |
| READ-05 | Phase 6 | Complete (06-01) |
| READ-06 | Phase 6 | Complete (06-02) |
| WRITE-01 | Phase 7 | Complete (07-01) |
| WRITE-02 | Phase 7 | Pending |
| WRITE-03 | Phase 7 | Pending |
| WRITE-04 | Phase 7 | Complete (07-01) |
| WRITE-05 | Phase 8 | Pending |
| WRITE-06 | Phase 8 | Pending |
| WRITE-07 | Phase 8 | Pending |
| STOR-01 | Phase 1 | Complete |
| STOR-02 | Phase 1 | Pending |
| STOR-03 | Phase 2 | Complete |

**Coverage:**
- v1 requirements: 23 total
- Mapped to phases: 23
- Unmapped: 0 ✓

---
*Requirements defined: 2026-10-09*
*Last updated: 2026-10-09 after initial definition*
