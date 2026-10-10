"""Booted-server E2E proofs over the real MCP protocol (09-04).

Spawns the real ``kb-mcp serve`` entry on a free localhost port with
hermetic tmp dirs (notes, token store, audit log), then drives all calls
through real streamable-http MCP clients carrying the ``x-api-token``
header. Proves SC-1 (all tools through MCP with auth), SC-2 (rate trip
over protocol), SC-3 (audit lines from real writes), SC-4 (client-safe
errors over protocol), and the transport half of SC-5 (booted server
serves real clients; live Desktop connect stays in 09-05).

Hermetic per run: unique free port, per-module tmp dirs, dedicated
tokens per test role (reader / writer / flood) so the rate-trip test
cannot poison other tests. The server subprocess is terminated in
``finally``; a boot failure fails loudly (no silent in-process
downgrade — SC-5 demands a booted server).
"""

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from kb_mcp.auth import TokenStore, TokenType

READER_RAW = "e2e-reader-token-0001-AAAAAAAAAAAAAAAA"
WRITER_RAW = "e2e-writer-token-0002-BBBBBBBBBBBBBBBB"
FLOOD_RAW = "e2e-flood-token-0003-CCCCCCCCCCCCCCCC"

EXPECTED_TOOLS = {
    "search_notes",
    "get_note",
    "list_notes",
    "get_tags",
    "create_note",
    "update_note",
    "delete_note",
    "add_tags",
    "remove_tags",
    "create_from_template",
}

ALPHA_BODY = "alpha body mentioning wombat-signal for search"
BETA_BODY = "plain beta body"


def _write_seed_note(notes_dir: Path, filename: str, title: str, tags: list, created: str, body: str) -> None:
    """Write one seed note file directly with valid YAML frontmatter."""
    tag_list = ", ".join(tags)
    content = f"---\ntitle: \"{title}\"\ntags: [{tag_list}]\ncreated: \"{created}\"\n---\n{body}\n"
    (notes_dir / filename).write_text(content, encoding="utf-8")


def _free_port() -> int:
    """Pick a unique free localhost port per run."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_port(port: int, proc: subprocess.Popen, timeout: float = 15.0) -> None:
    """Poll TCP readiness up to 15 s; fail loudly if the server exits."""
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"booted server exited early with code {proc.poll()}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return
        except OSError as e:
            last_error = str(e)
            time.sleep(0.25)
    raise RuntimeError(f"booted server not ready on 127.0.0.1:{port} within {timeout}s ({last_error})")


def _server_exe() -> list:
    """Resolve the real D-04 entry: installed ``kb-mcp serve`` first."""
    kb_mcp = shutil.which("kb-mcp")
    if kb_mcp:
        return [kb_mcp]
    # Fallback: same serve() entry through the interpreter.
    return [sys.executable, "-c", "from kb_mcp.server import serve; serve()"]


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    """Boot ``kb-mcp serve`` on a free port with seeded notes/tokens.

    Yields ``(base_url, raws, paths)``; terminates the subprocess in
    ``finally``. Env pins the server to tmp dirs only — the real
    home knowledge-base is never touched.
    """
    tmp_dir = tmp_path_factory.mktemp("e2e")
    notes_dir = tmp_dir / "notes"
    notes_dir.mkdir()
    _write_seed_note(notes_dir, "alpha.md", "Alpha", ["e2e", "work"], "2026-01-05", ALPHA_BODY)
    _write_seed_note(notes_dir, "beta.md", "Beta", ["e2e"], "2026-03-10", BETA_BODY)

    store_path = tmp_dir / "tokens.json"
    store = TokenStore(store_path=store_path)
    store.add_token(username="e2e-reader", token_type=TokenType.READ, raw=READER_RAW)
    store.add_token(username="e2e-writer", token_type=TokenType.READ_WRITE, raw=WRITER_RAW)
    store.add_token(username="e2e-flood", token_type=TokenType.READ, raw=FLOOD_RAW)

    audit_path = tmp_dir / "audit.log"
    port = _free_port()

    env = dict(os.environ)
    env["NOTES_DIR"] = str(notes_dir)
    env["KB_TOKENS_FILE"] = str(store_path)
    env["KB_AUDIT_FILE"] = str(audit_path)
    env["KB_HOST"] = "127.0.0.1"
    env["KB_PORT"] = str(port)
    # Fail-closed isolation: the booted server must serve the tmp notes.
    assert Path(env["NOTES_DIR"]) == notes_dir
    assert Path(env["KB_TOKENS_FILE"]) == store_path

    log_path = tmp_dir / "server.log"
    cmd = _server_exe() + ["serve", "--port", str(port), "--notes-dir", str(notes_dir)]
    with open(log_path, "wb") as log_handle:
        proc = subprocess.Popen(cmd, env=env, stdout=log_handle, stderr=subprocess.STDOUT)
    try:
        _wait_for_port(port, proc)
        base_url = f"http://127.0.0.1:{port}/mcp"
        raws = {"reader": READER_RAW, "writer": WRITER_RAW, "flood": FLOOD_RAW}
        paths = {"notes": notes_dir, "store": store_path, "audit": audit_path, "log": log_path}
        yield (base_url, raws, paths)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)


def _normalize_payload(result) -> dict:
    """Return the parsed result payload dict from a FastMCP call result."""
    if isinstance(result, dict):
        return result
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    data = getattr(result, "data", None)
    if isinstance(data, dict):
        return data
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            try:
                parsed = json.loads(text)
            except (ValueError, TypeError):
                continue
            if isinstance(parsed, dict):
                return parsed
    raise AssertionError(f"could not parse tool payload from {type(result)}: {result!r}")


def call_tool(base_url: str, name: str, args: dict, raw: str | None) -> dict:
    """Call one tool over real streamable-http MCP, returning the payload dict."""
    from fastmcp.client.transports import StreamableHttpTransport
    from fastmcp import Client

    headers = {"x-api-token": raw} if raw else None
    transport = StreamableHttpTransport(base_url, headers=headers) if headers else StreamableHttpTransport(base_url)

    async def _go():
        async with Client(transport) as client:
            result = await client.call_tool(name, args or {}, raise_on_error=False)
            return _normalize_payload(result)

    return asyncio.run(_go())


def list_tool_names(base_url: str, raw: str | None) -> list:
    """List registered tool names over the real protocol."""
    from fastmcp.client.transports import StreamableHttpTransport
    from fastmcp import Client

    headers = {"x-api-token": raw} if raw else None
    transport = StreamableHttpTransport(base_url, headers=headers) if headers else StreamableHttpTransport(base_url)

    async def _go():
        async with Client(transport) as client:
            tools = await client.list_tools()
            return [t.name for t in tools]

    return asyncio.run(_go())


def test_smoke_lists_all_ten_tools(live_server):
    base_url, raws, _ = live_server
    names = list_tool_names(base_url, raws["reader"])
    assert EXPECTED_TOOLS.issubset(set(names)), f"missing tools: {EXPECTED_TOOLS - set(names)}"


def test_smoke_unauthenticated_call_denied(live_server):
    base_url, _, _ = live_server
    payload = call_tool(base_url, "list_notes", {}, None)
    assert payload == {"success": False, "message": "Invalid or missing token."}


def _assert_no_traceback(payload: dict) -> None:
    """SC-4 blanket rule: no traceback text in any serialized response."""
    assert "Traceback" not in json.dumps(payload)


def test_e2e_reads_through_protocol(live_server):
    """SC-1 reads: search/get/list/tags succeed over MCP with a read token."""
    base_url, raws, _ = live_server
    reader = raws["reader"]

    found = call_tool(base_url, "search_notes", {"query": "wombat-signal"}, reader)
    _assert_no_traceback(found)
    assert any(r.get("filename") == "alpha" for r in found.get("results", []))

    note = call_tool(base_url, "get_note", {"title": "Beta"}, reader)
    _assert_no_traceback(note)
    assert note.get("found") is True
    assert BETA_BODY in (note.get("body") or "")

    listed = call_tool(base_url, "list_notes", {}, reader)
    _assert_no_traceback(listed)
    assert len(listed.get("notes", [])) == 2

    tags = call_tool(base_url, "get_tags", {}, reader)
    _assert_no_traceback(tags)
    tag_names = [t.get("tag") if isinstance(t, dict) else t for t in tags.get("tags", [])]
    assert "e2e" in tag_names


def test_e2e_writes_and_audit_lines(live_server):
    """SC-1 writes + SC-3 audit: real MCP writes append audit lines."""
    base_url, raws, paths = live_server
    writer = raws["writer"]

    created = call_tool(
        base_url, "create_note",
        {"title": "E2E Gamma", "body": "gamma body", "tags": ["e2e"]}, writer,
    )
    _assert_no_traceback(created)
    assert created.get("success") is True

    audit_text = paths["audit"].read_text(encoding="utf-8")
    assert "user=e2e-writer" in audit_text
    assert "tool=create_note" in audit_text
    assert "file=e2e-gamma" in audit_text

    tagged = call_tool(base_url, "add_tags", {"title": "E2E Gamma", "tags": ["extra"]}, writer)
    _assert_no_traceback(tagged)
    assert tagged.get("success") is True

    audit_lines = paths["audit"].read_text(encoding="utf-8").splitlines()
    assert any("tool=add_tags" in line for line in audit_lines)


def test_e2e_scope_and_missing_token_denials(live_server):
    """Locked denials over protocol: read-token-on-write + missing token."""
    base_url, raws, _ = live_server

    scoped = call_tool(base_url, "delete_note", {"title": "Beta"}, raws["reader"])
    _assert_no_traceback(scoped)
    assert scoped.get("success") is False
    assert scoped.get("message") == "Write access required. Use a write token or contact the owner."
    assert raws["reader"] not in json.dumps(scoped)

    missing = call_tool(base_url, "get_note", {"title": "Beta"}, None)
    _assert_no_traceback(missing)
    assert missing.get("message") == "Invalid or missing token."


def test_e2e_rate_limit_trip(live_server):
    """SC-2: the per-owner trip fires over the protocol on a dedicated token."""
    base_url, raws, _ = live_server
    flood = raws["flood"]
    tripped_at = None
    for attempt in range(1, 36):
        payload = call_tool(base_url, "get_tags", {}, flood)
        _assert_no_traceback(payload)
        message = payload.get("message") or ""
        if "Rate limit" in message:
            tripped_at = attempt
            assert "60" in message
            break
    assert tripped_at is not None, "rate trip never fired within 35 calls"


def test_e2e_client_safe_errors(live_server):
    """SC-4: expected failures are structured, messaged, and traceback-free."""
    base_url, raws, _ = live_server
    writer = raws["writer"]

    missing = call_tool(base_url, "get_note", {"title": "No Such Note XYZ"}, writer)
    assert missing.get("found") is False
    assert "not found" in (missing.get("message") or "").lower()
    _assert_no_traceback(missing)

    invalid = call_tool(base_url, "create_note", {"title": ""}, writer)
    assert invalid.get("success") is False
    assert "Invalid title" in (invalid.get("message") or "")
    _assert_no_traceback(invalid)
