"""Wrapper-level auth, scope, rate-trip, mapping, and secrecy proofs (09-03).

Every test drives the ``@mcp.tool()`` wrappers in :mod:`kb_mcp.server` (plain
functions) through the ``_invoke`` pipeline with a controlled token, proving
the transport wiring: valid tokens reach the gated tools, missing/bogus
tokens are denied fail-closed with the locked ``INVALID_TOKEN_MESSAGE``,
read-only tokens are denied from writes with the locked
``WRITE_DENIED_MESSAGE``, the per-owner rate trip returns
``RATE_LIMIT_MESSAGE``, unexpected errors map to traceback-free structured
payloads, and raw token secrets never reach logs or the audit file.

Hermetic per test: tmp repository (via ``configure_default_repo``), tmp token
store (``TokenStore.load`` patched), tmp audit file (``KB_AUDIT_FILE`` env),
and a reset rate limiter.
"""

import logging
import os
from pathlib import Path

import pytest

from kb_mcp import read_tools, server, write_tools
from kb_mcp.rate_limit import reset_rate_limits

INVALID_TOKEN_MESSAGE = "Invalid or missing token."
WRITE_DENIED_MESSAGE = "Write access required. Use a write token or contact the owner."


@pytest.fixture(autouse=True)
def _hermetic(repository, token_store, tmp_path, monkeypatch):
    """Isolate repos, store resolution, audit path, and limiter per test."""
    read_tools.configure_default_repo(repository)
    write_tools.configure_default_repo(repository)
    monkeypatch.setenv("KB_AUDIT_FILE", str(tmp_path / "audit.log"))
    reset_rate_limits()
    monkeypatch.setattr(
        server.TokenStore, "load", classmethod(lambda cls, *a, **k: token_store)
    )
    yield
    read_tools.configure_default_repo(None)
    write_tools.configure_default_repo(None)


def _use_token(monkeypatch, raw):
    """Patch header extraction to return a controlled raw token (or None)."""
    monkeypatch.setattr(server, "get_request_token", lambda: raw)


def _audit_text():
    path = Path(os.environ["KB_AUDIT_FILE"])
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def test_valid_read_token_lists_notes(repository, read_token_pair, monkeypatch):
    repository.write_note("hello.md", "Hello", "welcome body", ["greet"], "2026-02-01")
    raw, _ = read_token_pair
    _use_token(monkeypatch, raw)
    result = server.list_notes()
    assert "notes" in result
    assert any(n["filename"] == "hello" for n in result["notes"])


def test_missing_token_denied_fail_closed(monkeypatch):
    _use_token(monkeypatch, None)
    result = server.list_notes()
    assert result == {"success": False, "message": "Invalid or missing token."}


def test_bogus_token_denied_with_locked_message(monkeypatch):
    _use_token(monkeypatch, "bogus-token-not-in-store-0000")
    result = server.list_notes()
    assert result == {"success": False, "message": "Invalid or missing token."}


def test_read_token_denied_on_write_with_locked_message(read_token_pair, monkeypatch):
    raw, _ = read_token_pair
    _use_token(monkeypatch, raw)
    result = server.create_note(title="Nope Wont Write", body="x")
    assert result == {"success": False, "message": "Write access required. Use a write token or contact the owner."}


def test_write_token_creates_note_and_audits(read_write_token_pair, monkeypatch):
    raw, _ = read_write_token_pair
    _use_token(monkeypatch, raw)
    result = server.create_note(title="Auth Proof", body="hello", tags=["t"])
    assert result["success"] is True
    audit = _audit_text()
    assert "user=test-writer" in audit
    assert "tool=create_note" in audit


def test_rate_limit_trip_after_window_exhausted(read_token_pair, monkeypatch):
    raw, _ = read_token_pair
    _use_token(monkeypatch, raw)
    for _ in range(30):
        result = server.get_tags()
        assert "tags" in result
    tripped = server.get_tags()
    assert tripped.get("success") is False
    assert "Rate limit" in tripped["message"]


def test_unexpected_error_maps_without_traceback(read_token_pair, monkeypatch):
    raw, _ = read_token_pair
    _use_token(monkeypatch, raw)

    def _boom(**kwargs):
        raise RuntimeError("boom-trace-marker")

    monkeypatch.setattr(server, "_list_notes_gated", _boom)
    result = server.list_notes()
    assert result.get("success") is False
    assert "Internal error" in result["message"]
    assert "boom-trace-marker" in result["message"]
    assert "Traceback" not in result["message"]


def test_raw_token_never_reaches_logs_or_audit(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    raw_secret = "secrettest-raw-token-xyz-12345-abcdef"
    _use_token(monkeypatch, raw_secret)
    server.list_notes()
    server.create_note(title="Secrecy Probe", body="x")
    assert raw_secret not in _audit_text()
    assert raw_secret not in caplog.text


def test_read_logs_tool_name_only(repository, read_token_pair, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="kb_mcp.audit")
    caplog.set_level(logging.INFO, logger="kb_mcp.server")
    marker = "PLANTED-BODY-MARKER-98765"
    repository.write_note("planted.md", "Planted", f"body with {marker} inside", ["x"], "2026-01-01")
    raw, _ = read_token_pair
    _use_token(monkeypatch, raw)
    result = server.get_note("Planted")
    assert result.get("found") is True
    assert "get_note" in caplog.text
    assert marker not in caplog.text
