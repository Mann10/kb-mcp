# Knowledge Base MCP Server (`kb-mcp`)

An [MCP](https://modelcontextprotocol.io/) server that gives AI assistants (Claude, ChatGPT, etc.)
**read access** to a personal knowledge base of Markdown notes — while ensuring **only explicitly
authorized individuals can modify it** via scoped tokens.

- **Team members** get read-only tokens: search, read, list, browse tags.
- **Authorized individuals** get read+write tokens: create, update, delete, manage tags, use templates.
- Every tool call is authenticated, per-owner rate-limited, and audit-logged.

## Features

- **14 MCP tools** — 5 read, 9 write (see [MCP tools](#mcp-tools))
- **Scoped token auth** — `read` vs `read-write` tokens, hash-only storage, fail-closed on every call
- **Transport auth** — clients send the token in the `x-api-token` HTTP header; tool schemas stay clean
- **Rate limiting** — 30 requests / 60 s sliding window, keyed per token owner
- **Audit logging** — append-only `timestamp user tool file` lines, fail-open (audit never blocks a write)
- **Git versioning** — every write auto-commits via [dulwich](https://www.dulwich.io/) (pure Python, no git binary); fail-open
- **Atomic writes** — crash-safe temp-file + rename; path-traversal protection; slugified filenames
- **Note templates** — `meeting`, `book`, `idea` skeletons for quick capture,
  plus full CRUD (`list/create/update/delete_template`) backed by a persistent registry
- **Token CLI** — `generate`, `list`, `revoke`, `rotate` (+ `serve`)
- **296 tests** — unit, integration, and live booted-server end-to-end proofs

## Prerequisites

- **Python ≥ 3.12**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or `pip`
- A notes directory containing `*.md` files (or an empty dir to start fresh)
- An MCP client (e.g. Claude Desktop) for remote access — optional for local use

## Installation

```powershell
# Clone and enter the project
git clone <repo-url>
cd "storm mcp"

# Recommended: uv (creates .venv and installs the package + CLI)
uv sync

# Or: pip (editable install)
pip install -e .

# Dev extras (pytest)
pip install -e ".[dev]"
# or
uv sync --extra dev
```

This installs two console entry points (both map to `kb_mcp.cli:app`):

| Command | Purpose |
|---|---|
| `kb-mcp` | Full CLI: token management **and** `serve` |
| `kb-mcp-tokens` | Same app (lightweight alias; never imports FastMCP until `serve` runs) |

## Quickstart — start the project

### 1. Prepare a notes directory

The server **never creates** the notes directory — a missing or unwritable dir is a fail-fast
startup error (operator misconfiguration, not something to silently fix).

```powershell
# Use any directory you like
mkdir ~/knowledge-base/notes

# Point the server at it (or pass --notes-dir explicitly)
$env:NOTES_DIR = "$HOME/knowledge-base/notes"
```

Resolution order: `--notes-dir` flag → `NOTES_DIR` env var → `~/knowledge-base/notes` default.

Notes are plain Markdown files with YAML frontmatter (see [Note format](#note-format)):

```markdown
---
title: "My First Note"
tags: [ideas, mcp]
created: "2026-10-10"
---
Body text goes here.
```

### 2. Create a token

```powershell
# Read-only token for team members (default type is read)
kb-mcp generate alice

# Read+write token for yourself
kb-mcp generate bob --type read-write

# Token with expiry (30 days, 24 hours, 15 minutes, or raw seconds)
kb-mcp generate carol --type read-write --ttl 30d

# List tokens (display strings only — secrets are never shown again)
kb-mcp list
kb-mcp list --format json --all   # include revoked/expired
```

> The raw secret is printed **once** at generation time. Store it securely — it cannot be
> retrieved later (use `rotate` to replace it).

### 3. Start the server

```powershell
# Minimal (binds 0.0.0.0:8000, uses NOTES_DIR)
kb-mcp serve

# Explicit options (env vars KB_HOST / KB_PORT / NOTES_DIR act as defaults)
kb-mcp serve --host 127.0.0.1 --port 8000 --notes-dir "$HOME/knowledge-base/notes"
```

The server speaks **streamable-http** only, at `http://<host>:<port>/mcp`.
Startup fails fast with a clear message if `NOTES_DIR` is missing or not writable.

### 4. Connect a client

Clients must send their token in the **`x-api-token` HTTP header** on every request —
without it the server denies fail-closed. Include it in the client payload:

Example `claude_desktop_config.json` (see also `claude_desktop_config.example.json`):

```json
{
  "mcpServers": {
    "knowledge-base": {
      "transport": "streamable-http",
      "url": "http://localhost:8000/mcp",
      "headers": {
        "x-api-token": "<paste-your-token-here>"
      }
    }
  }
}
```

Replace `<paste-your-token-here>` with a token from `kb-mcp generate` (shown once at
generation time). Keep the real config file private — never commit secrets to git.

### 5. Verify it works

```powershell
# Run the full test suite (296 tests)
pytest

# Smoke-test token auth + tools without a client (Python REPL)
$env:NOTES_DIR = "$HOME/knowledge-base/notes"
python -c "from kb_mcp.read_tools import list_notes; print(list_notes(token='<raw-token>', _store=__import__('kb_mcp.auth', fromlist=['TokenStore']).TokenStore.load()))"
```

## MCP tools

All tools return structured dicts (`{"success": bool, "message": str, ...}`). Read tools need any
valid token; write tools need a `read-write` token.

### Read tools (any valid token)

| Tool | Signature | Description |
|---|---|---|
| `search_notes` | `(query="", limit=10, tag=None, date_from=None, date_to=None)` | Keyword search across body + title + stem + tags. Body matches rank first; `limit` defaults to 10, max 50. `tag` is normalized exact match; dates are `YYYY-MM-DD` and combine with AND. |
| `get_note` | `(title)` | Full note content by case-insensitive title/stem lookup (tolerates `.md` suffix and case variants). |
| `list_notes` | `()` | All notes, metadata only (no bodies), created-ascending. |
| `get_tags` | `()` | All tags with counts, sorted by `(-count, tag)`; first-seen casing displayed, counting is case-normalized. |
| `list_templates` | `()` | All templates (name, default tags, body skeleton), name-sorted. |

### Write tools (`read-write` token only)

| Tool | Signature | Description |
|---|---|---|
| `create_note` | `(title, body="", tags=None, created=None)` | Create a note; filename is slugified from the title; collisions are rejected with a structured exists-error. |
| `update_note` | `(title, new_title=None, body=None, tags=None, created=None)` | Update content/metadata; `new_title` renames via write-new + unlink-old in a **single** git commit. No-op updates succeed byte-identically. |
| `delete_note` | `(title)` | Delete by title/stem (same tolerant resolution as `get_note`). |
| `add_tags` | `(title, tags)` | Idempotent merge — caller casing stored verbatim, dedupe is case-insensitive; no-changes is still success. |
| `remove_tags` | `(title, tags)` | Idempotent removal (case-insensitive match); no-changes is still success. |
| `create_from_template` | `(template, title, body=None, tags=None, created=None)` | Create from a skeleton; `template` is any template in the registry (built-ins: `meeting`, `book`, `idea`). Supplied tags union with template defaults (dedupe, order-preserving). |
| `create_template` | `(name, body_skeleton="", default_tags=None)` | Create a template; names normalize to lowercase `[a-z0-9_-]`; duplicates rejected with a structured exists-error. |
| `update_template` | `(name, body_skeleton=None, default_tags=None)` | Partial update of a template (body and/or tags); no-op update is success. Missing names return the valid-templates list. |
| `delete_template` | `(name)` | Delete a template by name (case/whitespace-tolerant); notes already created from it are unaffected. |

## CLI reference

```
kb-mcp generate <username> [--type read|read-write] [--ttl 30d|24h|15m|3600]
kb-mcp list [--format table|json] [--all]
kb-mcp revoke <prefix>
kb-mcp rotate <prefix> [--ttl <ttl>]
kb-mcp serve [--host 0.0.0.0] [--port 8000] [--notes-dir <path>]
```

| Command | Details |
|---|---|
| `generate` | New token for `USERNAME`. `--type` defaults to `read` (fail-closed); `read-write` also accepts `read_write`. `--ttl` like `30d`, `24h`, `15m`, `3600` (bare number = seconds); omitted = never expires. Empty usernames rejected. |
| `list` | Active tokens by default; `--all` includes revoked/expired. Output shows `prefix...suffix` display strings only — never secrets. Fixed-width table renders intact when piped; `--format json` for scripting. |
| `revoke` | Revoke by prefix from `list` output (full secrets rejected — max 32 chars). Entry is kept, immediately invalid. Operational failures → stderr + exit 1; usage errors → exit 2. |
| `rotate` | Revoke old + print new secret in one step; identity and expiry carry over unless `--ttl` overrides. No `--type` flag (type is preserved). |
| `serve` | Start the server (streamable-http). `KB_HOST` / `KB_PORT` env vars override the flag defaults. |

## Note format

```markdown
---
title: "Design Notes"
tags: [architecture, mcp]
created: "2026-10-10"
---
Markdown body...
```

Validation rules (`NoteMetadata`, strict Pydantic model):

- `title` — non-empty after stripping whitespace
- `tags` — list of strings, each < 100 chars (whitespace-only tags rejected where filters apply)
- `created` — ISO 8601 date `YYYY-MM-DD`
- Filenames are slugified from the title; writes are atomic (temp file + rename) with
  path-traversal protection, and every mutation commits to git (fail-open — git never blocks a write).

## Configuration — environment variables

| Variable | Used by | Default | Description |
|---|---|---|---|
| `NOTES_DIR` | server, tools | `~/knowledge-base/notes` | Notes directory (must already exist and be writable). |
| `KB_TOKENS_FILE` | auth, CLI | platform app-data / home-based store | Token store JSON path. |
| `KB_TEMPLATES_FILE` | templates, server | `~/knowledge-base/templates.json` | Template registry JSON path (seeded with built-ins on first run). |
| `KB_AUDIT_FILE` | audit log | `~/knowledge-base/mcp_audit.log` | Append-only audit log path. |
| `KB_HOST` | `serve` | `0.0.0.0` | Bind host override. |
| `KB_PORT` | `serve` | `8000` | Bind port override. |

Client authentication: **`x-api-token` HTTP header** (per request; missing/invalid → fail-closed
denial, never pass-through).

## Development

```powershell
# Install dev deps + run tests
uv sync --extra dev
pytest                 # full suite (296 tests)
pytest tests/test_server_e2e.py   # live booted-server protocol proofs
pytest -q tests/test_read_tools.py  # single file
```

Conventions: branch-agnostic test assertions, `StringIO` for git-log capture, repos closed in
`finally`. Storage hooks are always-on (no constructor flag). See `tests/` (16 test modules)
and `src/kb_mcp/` for the implementation.

## Project structure

```
├── pyproject.toml                    # kb-mcp 0.1.0, Python ≥3.12, hatchling; scripts kb-mcp / kb-mcp-tokens
├── claude_desktop_config.example.json# streamable-http client snippet (http://localhost:8000/mcp)
├── src/kb_mcp/
│   ├── server.py       # FastMCP app, 14 thin wrappers, x-api-token auth, rate-limit + audit pipeline, serve()
│   ├── cli.py          # Typer operator CLI (generate/list/revoke/rotate/serve)
│   ├── auth.py         # Token model, hash-only TokenStore, verify, TTL, rotate, token_status
│   ├── middleware.py   # require_read / require_write decorators, locked denial strings
│   ├── read_tools.py   # search_notes / get_note / list_notes / get_tags (gated)
│   ├── templates.py    # TemplateStore registry + list/create/update/delete_template (gated)
│   ├── write_tools.py  # create/update/delete/tag tools (gated); create_from_template reads the template registry
│   ├── storage.py      # Filesystem source of truth, atomic writes, slugify, traversal guard
│   ├── parsing.py      # YAML frontmatter parsing (ruamel.yaml round-trip safe)
│   ├── models.py       # NoteMetadata / Note (strict Pydantic validation)
│   ├── validation.py   # Boundary validators (filenames, tags, dates)
│   ├── git_history.py  # dulwich auto-commits (fail-open), rename support
│   ├── rate_limit.py   # Per-owner 30 req/60 s sliding window, injectable clock
│   ├── audit.py        # Append-only audit log, mask_token secrecy choke point
│   └── errors.py       # AuthenticationError / AuthorizationError → client-safe payloads
├── tests/                        # 17 modules, 296 tests (unit + integration + live E2E)
└── .planning/                    # GSD project docs (ROADMAP, STATE, phases) — gitignored
```

## Architecture & security

```
MCP client ── x-api-token header ──▶ _invoke() ──▶ verify_token ──▶ per-owner rate check ──▶ gated tool
                                          │                │                    │                     │
                                       fail-closed      masked logs        30 req/60 s sliding      decorators
                                       denial strings   (no secrets)       window (fail-closed)     re-check scope
```

- **Defense in depth** — transport verification *and* unchanged `require_read`/`require_write`
  decorators on the gated tools; `TokenStore.load()` per call so revocations take effect immediately.
- **Locked denial strings** — auth/rate denials return verbatim messages (no user enumeration);
  unexpected errors return traceback-free `Internal error in <tool>` payloads (stack traces stay server-side).
- **Secrecy** — `mask_token()` is the single choke point; secrets never appear in logs, listings, or error messages.
- **Single-writer model** — no real-time collaboration, no web UI, no full-text search engine (keyword matching is sufficient by design).
- **Fail-open git + audit** — history and audit logging never block a note write; missing `NOTES_DIR` is the one fail-fast case (operator error).

## License / status

Personal knowledge-base project — milestone **v1.0 complete** (all 9 phases, verification 5/5).
See `.planning/ROADMAP.md` and `.planning/STATE.md` for the build history (gitignored local docs).
