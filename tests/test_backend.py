"""Backend dispatch + Horizon entrypoint tests (V2-03).

Filesystem-mode tests need no database. Supabase-mode tests only assert
dispatch (object types), never touching the network.
"""

import pytest

from kb_mcp import backend


def test_filesystem_is_default(monkeypatch):
    monkeypatch.delenv("KB_BACKEND", raising=False)
    assert backend.use_supabase() is False


def test_supabase_selected_case_insensitive(monkeypatch):
    monkeypatch.setenv("KB_BACKEND", "  Supabase ")
    assert backend.use_supabase() is True


def test_filesystem_stores(monkeypatch, tmp_path):
    from kb_mcp.auth import TokenStore
    from kb_mcp.storage import NoteRepository
    from kb_mcp.templates import TemplateStore

    monkeypatch.delenv("KB_BACKEND", raising=False)
    monkeypatch.setenv("NOTES_DIR", str(tmp_path / "notes"))
    assert isinstance(backend.get_token_store(), TokenStore)
    assert isinstance(backend.get_note_repository(), NoteRepository)
    assert isinstance(backend.get_template_store(), TemplateStore)


def test_supabase_stores_dispatched_without_io(monkeypatch):
    from kb_mcp.supabase_auth import SupabaseTokenStore
    from kb_mcp.supabase_notes import SupabaseNoteRepository
    from kb_mcp.supabase_templates import SupabaseTemplateStore

    monkeypatch.setenv("KB_BACKEND", "supabase")
    assert isinstance(backend.get_token_store(), SupabaseTokenStore)
    assert isinstance(backend.get_note_repository(), SupabaseNoteRepository)
    assert isinstance(backend.get_template_store(), SupabaseTemplateStore)


def test_horizon_entry_import_filesystem(monkeypatch):
    import sys

    monkeypatch.delenv("KB_BACKEND", raising=False)
    from kb_mcp import read_tools, templates, write_tools

    saved = (
        read_tools._default_repo,
        write_tools._default_repo,
        templates._configured_store,
    )
    sys.modules.pop("kb_mcp.horizon_entry", None)
    try:
        import kb_mcp.horizon_entry as entry

        assert entry.mcp.name == "KnowledgeBase"
        assert read_tools._default_repo is None
        assert templates._configured_store is None
    finally:
        read_tools.configure_default_repo(saved[0])
        write_tools.configure_default_repo(saved[1])
        templates.configure_template_store(saved[2])


def test_list_stems_and_exists_filesystem(tmp_path):
    from kb_mcp.storage import NoteRepository

    repo = NoteRepository(notes_dir=tmp_path / "notes")
    assert repo.list_stems() == []
    assert repo.stem_exists("nope") is False
    repo.write_note("b-note.md", "B", "", [], "2026-10-12")
    repo.write_note("a-note.md", "A", "", [], "2026-10-10")
    assert repo.list_stems() == ["a-note", "b-note"]
    assert repo.stem_exists("a-note") is True


def test_actor_accepted_filesystem(tmp_path):
    """Actor threads through write tools without changing file behavior."""
    from kb_mcp import write_tools
    from kb_mcp.storage import NoteRepository

    repo = NoteRepository(notes_dir=tmp_path / "notes")
    write_tools.configure_default_repo(repo)
    try:
        result = write_tools.create_note.__wrapped__(
            "Actor Note", "body", ["t"], "2026-10-11",
            token=None, _store=None, actor="alice",
        )
        assert result["success"] is True
    finally:
        write_tools.configure_default_repo(None)
