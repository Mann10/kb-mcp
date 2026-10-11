# Deploy kb-mcp to Prefect Horizon (Supabase backend)

Stateless server on Horizon + all state in Supabase. No disks, no volumes —
Horizon's hosted contract is ephemeral local files, and this setup keeps
nothing local.

## Prerequisites

- Horizon account (`horizon.prefect.io`, GitHub sign-in) with an organization.
- Horizon GitHub App granted access to `Mann10/kb-mcp` (public repo is fine).
- Supabase project with migrations `0001`–`0003` applied (`supabase db push`).
- The **pooler** connection string (NOT direct-5432):
  `postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres`

## Create the server

1. Registry → **Build and deploy** (Hosted card).
2. Select the `kb-mcp` repository, branch `master`.
3. Configure:
   - **Name:** `kb-mcp` → URL `https://kb-mcp.fastmcp.app/mcp`
   - **Entrypoint:** `src/kb_mcp/horizon_entry.py:mcp`
   - **Dependencies:** `pyproject.toml`
   - **Python:** 3.12+
4. Environment Variables (Production):
   - `KB_BACKEND` = `supabase`
   - `SUPABASE_DB_URL` = pooler URL above (secret — never commit it)
5. Deploy. First build inspects the entrypoint by importing it — the import
   performs zero I/O (stores resolve lazily per request), so inspection succeeds
   with or without database access.
6. Verify: Deployments page → Live URL → paste into MCP Inspector
   (`npx @modelcontextprotocol/inspector@latest`), list tools (expect 14).

## Clients

On the free tier Horizon authentication stays ON (disabling needs a paid plan),
so every client sends **two** credentials:

- Horizon: interactive sign-in, or a Horizon **API key** as bearer token
  (mint in dashboard) for non-interactive clients.
- kb-mcp: `x-api-token` header with a token from the `tokens` table. Seed the
  first owner token directly in Supabase (SQL Editor), reusing the CLI's format
  — or temporarily point a local checkout at the pooler URL and run
  `kb-mcp generate <name> --type read-write` with `KB_BACKEND=supabase` set.

## Share with a teammate (one-shot client setup)

Prerequisites on their machine: Node.js 18+ and Claude Desktop. Then:

1. Install the bridge globally (avoids the `npx` + spaces-in-path trap on Windows):
   ```
   npm install -g mcp-remote
   ```
2. Paste this into their Claude Desktop config
   (`%APPDATA%\Claude\claude_desktop_config.json` on Windows,
   `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS),
   filling in the two secrets you issue them:
   ```json
   {
     "mcpServers": {
       "knowledge-base": {
         "command": "mcp-remote",
         "args": [
           "https://<your-server>.fastmcp.app/mcp",
           "--header",
           "Authorization:Bearer ${HORIZON_KEY}",
           "--header",
           "x-api-token:${KB_TOKEN}"
         ],
         "env": {
           "HORIZON_KEY": "<their-horizon-api-key>",
           "KB_TOKEN": "<their-kb-token>"
         }
       }
     }
   }
   ```
   Notes: no spaces after the colons in the header args (Windows arg-mangling
   workaround); secrets live in `env`, where spaces are safe. `mcp-remote`
   substitutes `${...}` from `env` itself.
3. Fully quit Claude Desktop from the tray and reopen.
4. First launch may open a browser for Horizon's one-time OAuth; afterwards the
   credential is cached and launches are silent.

What you (the owner) must issue per person: a Horizon API key (dashboard →
avatar → API Keys) with server access, plus a KB token
(`kb-mcp generate <name>` with `KB_BACKEND=supabase`, read or read-write).

## Day-2 notes

- Every push to `master` builds a new artifact; promote/roll back from Deployments.
- Request window is 170 s, memory 1024 MB — ample for note operations.
- Rate limiting is per-instance in-memory (documented tradeoff; under-enforces
  under autoscale — revisit only if abuse is observed).
- Audit: note writes land in the `audit_log` table; Horizon request/server logs
  cover auth denials and rate-limit hits.
- Revision history: every mutation writes a `note_revisions` row with the actor
  (token owner). No git on Horizon — that lives on in local filesystem runs.
