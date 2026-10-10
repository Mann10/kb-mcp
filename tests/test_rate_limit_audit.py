"""Limiter isolation, audit lines, and secrecy proofs for 09-02."""

import logging

from kb_mcp.audit import (
    audit_write,
    log_denial,
    log_read,
    mask_token,
)
from kb_mcp.rate_limit import (
    RATE_LIMIT_MESSAGE,
    check_rate_limit,
    reset_rate_limits,
)

RAW = "test-raw-token-AAAABBBBCCCCDDDD"


def test_window_allow_then_deny():
    reset_rate_limits()
    results = [check_rate_limit("alice", now=1000.0 + i) for i in range(30)]
    assert all(results)
    assert check_rate_limit("alice", now=1000.0 + 30) is False


def test_sliding_expiry_allows_again():
    reset_rate_limits()
    for i in range(30):
        assert check_rate_limit("alice", now=1000.0 + i) is True
    assert check_rate_limit("alice", now=1000.0 + 30) is False
    # Window slides: timestamps at 1000..1029 are all older than 61s at t=1061.
    assert check_rate_limit("alice", now=1000.0 + 61.0) is True


def test_owner_isolation():
    reset_rate_limits()
    for i in range(30):
        assert check_rate_limit("alice", now=2000.0 + i) is True
    assert check_rate_limit("alice", now=2000.0 + 30) is False
    # owner buckets are independent: bob unaffected by alice exhaustion.
    assert check_rate_limit("bob", now=2000.0 + 30) is True


def test_empty_key_rejected():
    reset_rate_limits()
    for bad in ("", "   "):
        try:
            check_rate_limit(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"empty key {bad!r} did not raise ValueError")


def test_rate_limit_message_content():
    assert "Rate limit" in RATE_LIMIT_MESSAGE
    assert "60" in RATE_LIMIT_MESSAGE


def test_audit_line_shape(tmp_path):
    log_file = tmp_path / "t.log"
    audit_write("alice", "create_note", "x.md", log_path=log_file)
    content = log_file.read_text(encoding="utf-8")
    assert "user=alice" in content
    assert "tool=create_note" in content
    assert "file=x.md" in content
    # Timestamp carries a 4-digit year.
    assert "202" in content or "203" in content


def test_audit_fail_open_on_directory_path(tmp_path):
    # Pointing log_path at a directory makes the append raise OSError
    # internally; it must never escape to the caller.
    audit_write("alice", "create_note", "x.md", log_path=tmp_path)


def test_mask_token_secrecy():
    masked = mask_token(RAW)
    assert masked != RAW
    assert RAW not in masked
    assert "..." in masked
    assert mask_token(None) == "missing"
    assert mask_token("") == "missing"


def test_log_denial_never_logs_raw(caplog):
    with caplog.at_level(logging.WARNING, logger="kb_mcp.audit"):
        log_denial("auth", "alice", "get_note", mask_token(RAW))
    assert RAW not in caplog.text


def test_log_read_light_verbosity(caplog):
    with caplog.at_level(logging.INFO, logger="kb_mcp.audit"):
        log_read("search_notes")
    assert "search_notes" in caplog.text
    assert "body-secret" not in caplog.text
