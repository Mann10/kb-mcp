"""CliRunner proofs for the kb-mcp-tokens operator CLI (Phase 04 Plan 02)."""

import json

import pytest
from typer.testing import CliRunner

from kb_mcp.auth import TokenStore, TokenType
from kb_mcp.cli import app


@pytest.fixture
def isolated_cli_env(tmp_path, monkeypatch):
    """Isolate the token store per test via KB_TOKENS_FILE override."""
    monkeypatch.setenv("KB_TOKENS_FILE", str(tmp_path / ".tokens.json"))
    return CliRunner()


def _raw_from_generate_output(stdout: str, username: str) -> str:
    """Extract the one-time raw secret from generate/rotate stdout."""
    marker_new = f"New token for '{username}': "
    for line in stdout.splitlines():
        if line.startswith(marker_new):
            return line.split(": ", 1)[1].strip()
    marker = f"Token for '{username}': "
    for line in stdout.splitlines():
        if line.startswith(marker):
            return line.split(": ", 1)[1].strip()
    raise AssertionError(f"no raw token line for {username!r} in:\n{stdout}")


def _prefix_of_display(token_display: str) -> str:
    """Recover the 8-char prefix from a 'prefix...suffix' display string."""
    return token_display.split("...")[0]


def test_generate_defaults_to_read(isolated_cli_env, tmp_path):
    """Bare generate mints a read-only token shown once, never in the file."""
    runner = isolated_cli_env
    result = runner.invoke(app, ["generate", "cli-alice"])
    assert result.exit_code == 0, result.output
    assert "Store this token securely" in result.output
    raw = _raw_from_generate_output(result.output, "cli-alice")
    store = TokenStore.load()
    entries = store.list_entries(include_revoked_expired=True)
    assert len(entries) == 1
    assert entries[0].token_type == TokenType.READ
    store_file = tmp_path / ".tokens.json"
    assert raw not in store_file.read_text(encoding="utf-8")


def test_generate_read_write_and_ttl(isolated_cli_env):
    """--type read-write and --ttl 30d mint expiring write tokens; bad flags mint nothing."""
    runner = isolated_cli_env
    result = runner.invoke(app, ["generate", "cli-bob", "--type", "read-write", "--ttl", "30d"])
    assert result.exit_code == 0, result.output
    store = TokenStore.load()
    entries = store.list_entries(include_revoked_expired=True)
    assert len(entries) == 1
    assert entries[0].token_type == TokenType.READ_WRITE
    assert entries[0].expires_at is not None

    before = len(TokenStore.load())
    bad_ttl = runner.invoke(app, ["generate", "cli-bad", "--type", "read", "--ttl", "99x"])
    assert bad_ttl.exit_code != 0
    assert len(TokenStore.load()) == before

    bad_type = runner.invoke(app, ["generate", "cli-bad", "--type", "superuser"])
    assert bad_type.exit_code != 0
    assert len(TokenStore.load()) == before


def test_list_table_and_json_hide_secrets(isolated_cli_env):
    """Table and JSON list outputs show display strings, never raws or key_hash."""
    runner = isolated_cli_env
    r1 = runner.invoke(app, ["generate", "cli-alice"])
    r2 = runner.invoke(app, ["generate", "cli-bob", "--type", "read-write"])
    assert r1.exit_code == 0 and r2.exit_code == 0
    raw1 = _raw_from_generate_output(r1.output, "cli-alice")
    raw2 = _raw_from_generate_output(r2.output, "cli-bob")

    table = runner.invoke(app, ["list"])
    assert table.exit_code == 0, table.output
    assert "cli-alice" in table.output and "cli-bob" in table.output
    assert "..." in table.output
    assert raw1 not in table.output and raw2 not in table.output
    assert "key_hash" not in table.output

    as_json = runner.invoke(app, ["list", "--format", "json"])
    assert as_json.exit_code == 0, as_json.output
    payload = json.loads(as_json.output)
    assert len(payload) == 2
    expected_keys = {
        "token_display",
        "username",
        "token_type",
        "created_at",
        "last_used_at",
        "expires_at",
        "status",
    }
    for item in payload:
        assert set(item.keys()) == expected_keys
        assert "key_hash" not in item
    displays = [item["token_display"] for item in payload]
    assert any("..." in d for d in displays)
    assert raw1 not in as_json.output and raw2 not in as_json.output


def test_list_all_includes_revoked_and_expired(isolated_cli_env):
    """Default list hides revoked+expired; --all reveals them with status strings."""
    runner = isolated_cli_env
    g1 = runner.invoke(app, ["generate", "cli-alice"])
    g2 = runner.invoke(app, ["generate", "cli-bob"])
    assert g1.exit_code == 0 and g2.exit_code == 0
    raw1 = _raw_from_generate_output(g1.output, "cli-alice")
    _raw_from_generate_output(g2.output, "cli-bob")

    prefix1 = raw1[:8]
    revoked = runner.invoke(app, ["revoke", prefix1])
    assert revoked.exit_code == 0, revoked.output

    store = TokenStore.load()
    bob_entries = [e for e in store.list_entries(include_revoked_expired=True) if e.username == "cli-bob"]
    assert len(bob_entries) == 1
    bob_entries[0].expires_at = "2000-01-01T00:00:00+00:00"
    store.save()

    default = runner.invoke(app, ["list"])
    assert default.exit_code == 0
    assert "cli-alice" not in default.output and "cli-bob" not in default.output

    everything = runner.invoke(app, ["list", "--all"])
    assert everything.exit_code == 0, everything.output
    assert "cli-alice" in everything.output and "cli-bob" in everything.output
    assert "revoked" in everything.output and "expired" in everything.output


def test_revoke_by_prefix_denies_lookup(isolated_cli_env):
    """Revoke by prefix invalidates immediately while keeping the entry."""
    runner = isolated_cli_env
    gen = runner.invoke(app, ["generate", "cli-alice"])
    assert gen.exit_code == 0
    raw = _raw_from_generate_output(gen.output, "cli-alice")

    listed = runner.invoke(app, ["list", "--format", "json"])
    assert listed.exit_code == 0
    payload = json.loads(listed.output)
    assert len(payload) == 1
    prefix = _prefix_of_display(payload[0]["token_display"])

    revoked = runner.invoke(app, ["revoke", prefix])
    assert revoked.exit_code == 0, revoked.output

    store = TokenStore.load()
    assert store.lookup(raw) is None
    kept = [e for e in store.list_entries(include_revoked_expired=True) if e.username == "cli-alice"]
    assert len(kept) == 1
    assert kept[0].revoked_at is not None


def test_revoke_unknown_and_ambiguous_fail_safely(isolated_cli_env):
    """Unknown and ambiguous prefixes fail non-zero with zero mutation."""
    runner = isolated_cli_env
    store = TokenStore.load()
    store.add_token(username="shared-alice", token_type=TokenType.READ, raw="test-aaaa-shared-0001")
    store.add_token(username="shared-bob", token_type=TokenType.READ, raw="test-bbbb-shared-0002")
    assert len(TokenStore.load()) == 2

    unknown = runner.invoke(app, ["revoke", "zzzz"])
    assert unknown.exit_code != 0
    combined_unknown = unknown.output + (unknown.stderr or "")
    assert "No token found" in combined_unknown
    assert len(TokenStore.load()) == 2

    ambiguous = runner.invoke(app, ["revoke", "test"])
    assert ambiguous.exit_code != 0
    combined_ambiguous = ambiguous.output + (ambiguous.stderr or "")
    assert "Ambiguous" in combined_ambiguous
    assert len(TokenStore.load()) == 2


def test_rotate_carries_identity_single_command(isolated_cli_env):
    """Rotate revokes the old token and prints the new secret once with identity carried over."""
    runner = isolated_cli_env
    gen = runner.invoke(app, ["generate", "cli-alice"])
    assert gen.exit_code == 0
    old_raw = _raw_from_generate_output(gen.output, "cli-alice")

    listed = runner.invoke(app, ["list", "--format", "json"])
    assert listed.exit_code == 0
    payload = json.loads(listed.output)
    assert len(payload) == 1
    prefix = _prefix_of_display(payload[0]["token_display"])
    old_type = payload[0]["token_type"]

    rotated = runner.invoke(app, ["rotate", prefix])
    assert rotated.exit_code == 0, rotated.output
    assert "Store this token securely" in rotated.output
    new_raw = _raw_from_generate_output(rotated.output, "cli-alice")
    assert new_raw != old_raw

    store = TokenStore.load()
    assert store.lookup(old_raw) is None
    new_entry = store.lookup(new_raw)
    assert new_entry is not None
    assert new_entry.username == "cli-alice"
    assert new_entry.token_type.value == old_type
    all_entries = [e for e in store.list_entries(include_revoked_expired=True) if e.username == "cli-alice"]
    assert len(all_entries) == 2
    assert sum(1 for e in all_entries if e.revoked_at is not None) == 1
