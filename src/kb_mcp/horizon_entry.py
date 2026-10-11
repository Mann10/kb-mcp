"""Horizon entrypoint (V2-03): ``src/kb_mcp/horizon_entry.py:mcp``.

Horizon builds inspect the entrypoint by IMPORTING it — ``serve()`` is never
called. So this module must be import-safe:

- No ``SystemExit``, no network I/O, no database access at import time.
- Tool registration happens in :mod:`kb_mcp.server` at import (decorators),
  independent of any store.
- Stores resolve lazily per request from ``KB_BACKEND`` / ``SUPABASE_DB_URL``.

Required Horizon env vars: ``KB_BACKEND=supabase``,
``SUPABASE_DB_URL`` (pooler URL). Without them the app still imports and
inspects fine, serving the filesystem backend wherever it runs.
"""

from kb_mcp import server
from kb_mcp.backend import use_supabase

if use_supabase():
    # Pre-wire Supabase objects (constructors perform no I/O; template
    # seeding is lazy on first use) so request paths work without serve().
    from kb_mcp import read_tools, templates, write_tools
    from kb_mcp.backend import get_note_repository, get_template_store

    _repo = get_note_repository()
    read_tools.configure_default_repo(_repo)
    write_tools.configure_default_repo(_repo)
    templates.configure_template_store(get_template_store())
    del _repo

mcp = server.mcp

__all__ = ["mcp"]
