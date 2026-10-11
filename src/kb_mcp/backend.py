"""Backend dispatch (V2-03).

``KB_BACKEND=supabase`` routes every store entry point to Supabase Postgres;
anything else (including unset) keeps the v1 filesystem behavior byte-identical.
Read at call time (never import time) so tests can flip it per-case.

Horizon sets ``KB_BACKEND=supabase`` + ``SUPABASE_DB_URL`` (pooler URL) via
encrypted env vars. Local runs never set it and notice nothing.
"""

import os

from .auth import TokenStore
from .storage import NoteRepository
from .supabase_notes import SupabaseNoteRepository

NoteRepo = NoteRepository | SupabaseNoteRepository


def use_supabase() -> bool:
    """True only when the Supabase backend is explicitly selected."""
    return os.environ.get("KB_BACKEND", "").strip().lower() == "supabase"


def get_token_store() -> TokenStore:
    """Token store for the active backend (per-call, revocation-immediate)."""
    if use_supabase():
        from .supabase_auth import SupabaseTokenStore

        return SupabaseTokenStore.load()  # type: ignore[return-value]
    return TokenStore.load()


def get_note_repository() -> NoteRepo:
    """Note repository for the active backend."""
    if use_supabase():
        return SupabaseNoteRepository()
    return NoteRepository()


def get_template_store():
    """Template store for the active backend (built-ins always present)."""
    if use_supabase():
        from .supabase_templates import SupabaseTemplateStore

        return SupabaseTemplateStore.load()
    from .templates import TemplateStore

    return TemplateStore.load()


__all__ = [
    "NoteRepo",
    "get_note_repository",
    "get_template_store",
    "get_token_store",
    "use_supabase",
]
