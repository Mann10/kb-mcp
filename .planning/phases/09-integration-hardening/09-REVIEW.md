---
phase: 09-integration-hardening
reviewed: 2026-10-10T00:00:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - src/kb_mcp/server.py
  - src/kb_mcp/cli.py
  - src/kb_mcp/rate_limit.py
  - src/kb_mcp/audit.py
  - tests/test_rate_limit_audit.py
  - tests/test_server_auth.py
  - tests/test_server_e2e.py
  - pyproject.toml
findings:
  critical: 1
  warning: 10
  info: 8
  total: 19
status: issues_found
---

# Phase 09: Code Review Report

**Reviewed:** 2026-10-10T00:00:00Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

Reviewed the Phase 9 integration-hardening surface at standard depth: the MCP
transport wiring (`server.py`), the operator CLI (`cli.py`), the rate limiter
(`rate_limit.py`), the audit module (`audit.py`), three test files, and
`pyproject.toml`. Cross-referenced `middleware.py`, `auth.py`, and `errors.py`
to verify the claims made in docstrings (fail-closed auth, locked denial
strings, secrecy choke points).

No authentication bypass was found: header extraction denies fail-closed,
scope checks are defense-in-depth (transport verify + unchanged decorators),
and raw secrets are correctly routed through `mask_token` on every log path in
`server.py`. The test suite proves the auth pipeline, rate trip, and secrecy
properties it claims — with one coverage overclaim noted below (IN-05).

The headline defect is **audit integrity**: failed writes (e.g. `create_note`
with an invalid title, which returns `{"success": False}` rather than raising)
are appended to the append-only audit log as if they succeeded (CR-01). Around
it sits a cluster of robustness gaps in the same security features: the
rate-limit `ValueError` escapes the client-safe error mapping (WR-01), the
audit fail-open catches only `OSError` (WR-04), audit lines are injectable via
unsanitized usernames (WR-03), and `mask_token` reveals the whole secret for
8-character tokens (WR-02). The CLI has two unhandled operator-input crashes
(WR-05, WR-06), and both `serve` entry points default to binding `0.0.0.0`
with cleartext bearer tokens (WR-09).

## Critical Issues

### CR-01: Failed writes are audit-logged as successful writes

**File:** `src/kb_mcp/server.py:165-176`
**Issue:** `_invoke` calls `log_write` / `audit_write` for every `is_write`
call whose gated function returns without raising — it never inspects
`result["success"]`. But gated write tools signal validation failures by
returning `{"success": False, ...}` dicts, not by raising (proven by
`test_e2e_client_safe_errors`: `create_note` with `title=""` returns
`success=False` with `"Invalid title"` over the protocol). So every rejected
write appends a `user=... tool=create_note file=...` line to the append-only
audit log for a note that was never created, and the `filename_of` fallback
logs a bogus `file=create_note` when the failure dict has no `filename` key.
The D-15 audit trail — the forensic record this phase exists to provide —
accumulates false entries that assert writes happened when they did not.
**Fix:**
```python
if is_write:
    if not (isinstance(result, dict) and result.get("success") is True):
        return result  # rejected writes leave no audit trace
    if filename_of is not None and isinstance(result, dict):
        ...
```

## Warnings

### WR-01: Rate-limit `ValueError` escapes client-safe error mapping

**File:** `src/kb_mcp/server.py:153-156`
**Issue:** The `check_rate_limit(user)` call sits *before* the `try` block, so
the `ValueError` it raises for an empty/whitespace key propagates out of
`_invoke` uncaught — bypassing the D-17 structured-error mapping and reaching
the FastMCP layer as an unhandled exception (traceback text to the client,
per the SC-4 blanket rule the e2e suite enforces everywhere else). Reachable
today only via a degenerate (empty-username) token entry, but the fail-closed
contract of `rate_limit.py` ("anonymous callers raise") assumes the caller
handles it, and this caller does not.
**Fix:**
```python
try:
    rate_ok = check_rate_limit(user)
except ValueError:
    log_denial("rate-limit", user, tool_name, mask_token(raw))
    return {"success": False, "message": RATE_LIMIT_MESSAGE}
if not rate_ok:
    ...
```

### WR-02: `mask_token` reveals the entire secret for 8-character tokens

**File:** `src/kb_mcp/audit.py:36-40`
**Issue:** For `len(raw) >= 8` the mask is `raw[:4]...raw[-4:]`. When
`len(raw) == 8`, first-4 plus last-4 is the *whole token* — the "masked"
value logged by `log_denial` contains the full secret. Length 9 leaks 8 of 9
characters. Production tokens are 43 chars so the blast radius today is
limited to short/operator-supplied tokens, but the central secrecy primitive
(D-18) must be safe for all inputs by construction.
**Fix:**
```python
if len(raw) >= 12:
    return f"{raw[:4]}...{raw[-4:]}"
return "****"
```

### WR-03: Audit lines are forgeable via unsanitized usernames (log injection)

**File:** `src/kb_mcp/audit.py:56`
**Issue:** `audit_write` interpolates `username`, `tool`, and `filename`
verbatim into a newline-delimited log line, but nothing constrains the
username charset: `cli.py generate` accepts any non-empty string
(`cli.py:79-80` checks only `username.strip()`), and `TokenEntry` validates
only non-emptiness. A username like `"alice\n2026-01-01 user=bob tool=delete_note
file=x"` (or one containing `\r`, `user=` fragments) splits/forges audit
records in the append-only log, undermining exactly the forensic property
D-15 exists for.
**Fix:** Sanitize at the choke point and constrain at creation, e.g.
```python
safe_user = "".join(c for c in username if c.isprintable()).replace("\n", "_") ...
# and in auth.py username validator: reject with `re.fullmatch(r"[A-Za-z0-9._-]+", stripped)`
```

### WR-04: Audit fail-open catches only `OSError` — `ValueError` escapes

**File:** `src/kb_mcp/audit.py:57-63`
**Issue:** The docstring promises "fail-open: an OSError warns and returns so
audit never blocks a write", and the `except` clause matches only `OSError`.
But a malformed `KB_AUDIT_FILE` (embedded null byte, unencodable path) raises
`ValueError` — from `Path(env_path)` in `audit_log_path()` or from
`path.open()` — which is *not* caught. Worse, `log_write` is called from
`_invoke` *after* the gated tool already succeeded and *outside* its `try`
block, so the escaping `ValueError` converts a successful write into a client
error (and a potential traceback over the protocol), i.e. audit fails
*closed* on exactly the inputs the fail-open contract should absorb.
**Fix:**
```python
except Exception as e:  # fail-open: audit must never block a write
    logger.warning("audit append failed: %s", e)
    return
```

### WR-05: `cli serve` crashes with a traceback on non-numeric `KB_PORT`

**File:** `src/kb_mcp/cli.py:188-190`
**Issue:** `resolved_port = int(os.environ.get("KB_PORT", port))` raises a bare
`ValueError` for `KB_PORT=abc` (or `"8000.5"`), and there is no range check
(0, negative, >65535 surface later as an obscure bind `OSError`). An operator
typo in env config — the primary configuration path for this command — yields
a Python traceback instead of a clean operator error. Same line leaves
`KB_HOST=""` unvalidated (binds the wildcard).
**Fix:**
```python
try:
    resolved_port = int(os.environ.get("KB_PORT", port))
except ValueError:
    raise typer.BadParameter(f"Invalid KB_PORT {os.environ.get('KB_PORT')!r}: must be an integer 1-65535")
if not 1 <= resolved_port <= 65535:
    raise typer.BadParameter(...)
```

### WR-06: `parse_ttl_duration` crashes with `OverflowError` on huge TTLs

**File:** `src/kb_mcp/cli.py:37-46`
**Issue:** `_TTL_RE` accepts an unbounded digit string, and
`timedelta(seconds=amount * _MULT[unit])` raises `OverflowError` for values
past `timedelta.max` (e.g. `--ttl 9999999999d`, ~10^10 days). The function
promises `BadParameter` for bad input but this input class escapes as a
traceback. `"0s"` (immediately-expired token) is also silently accepted — an
operator footgun worth at least a warning.
**Fix:**
```python
try:
    return timedelta(seconds=amount * _MULT[unit])
except OverflowError:
    raise typer.BadParameter(f"TTL '{value}' is out of range")
```

### WR-07: `ensure_notes_dir` accepts a regular file as `NOTES_DIR`

**File:** `src/kb_mcp/server.py:41-51`
**Issue:** The fail-fast check tests `path.exists()` and writability but never
`path.is_dir()`. Pointing `NOTES_DIR` at an existing writable *file* passes
both gates, and the failure then surfaces later inside `NoteRepository` as an
obscure error instead of the clear operator message D-06 requires.
**Fix:**
```python
if not path.is_dir():
    raise SystemExit(f"NOTES_DIR '{path}' is not a directory: ...")
```

### WR-08: Header fallback is case-insensitive in attempt 1 only

**File:** `src/kb_mcp/server.py:93-127`
**Issue:** Attempt 1 has a case-insensitive `headers.items()` fallback loop
(lines 85-90), but attempts 2 (`_current_context`, lines 99-108) and 3
(`get_http_request`, lines 116-124) use only the exact `headers.get(
"x-api-token")` lookup. Against a case-sensitive header mapping carrying
`X-Api-Token`, whichever attempt actually resolves the request context misses
a present token and the caller is denied fail-closed despite supplying valid
credentials — an intermittent, host-dependent auth failure. (Starlette's
own mapping is case-insensitive, so this bites only on non-Starlette/later
mappings — but attempt 1's loop proves that case was already a concern.)
**Fix:** Extract a `_get_header(headers)` helper with the exact-then-
case-insensitive logic and use it in all three attempts.

### WR-09: Both `serve` entry points default to binding `0.0.0.0` over cleartext HTTP

**File:** `src/kb_mcp/server.py:324` and `src/kb_mcp/cli.py:176-178`
**Issue:** Default host `0.0.0.0` exposes the bearer-token-authenticated
service on all interfaces, while the protocol is plain HTTP with the token in
the `x-api-token` header on every call — any LAN eavesdropper recovers a
replayable credential, and there is no TLS option anywhere in the serve path.
For a single-user personal KB the safe default is loopback.
**Fix:** Default host to `"127.0.0.1"` in both signatures and document that
`0.0.0.0` requires the operator to front TLS:
```python
def serve(host: str = "127.0.0.1", port: int = 8000, ...) -> None:
```

### WR-10: Unexpected-error mapping echoes storage internals to clients

**File:** `src/kb_mcp/server.py:162-164`
**Issue:** `f"Internal error in {tool_name}: {e}."` embeds the raw exception
message in the client payload. Storage exceptions carry server-side detail —
`FileIOError` embeds the OS strerror, `PathTraversalError`/`NoteNotFoundError`
embed paths/filenames (absolute `NOTES_DIR` layout) — so any authenticated
caller, including a low-privilege read token, learns filesystem internals.
(The suite even locks this in: `test_server_auth.py:117` *requires* the
marker in the message.) D-17 keeps the stack trace server-side but the message
half of the leak remains.
**Fix:** Return a fixed opaque payload and keep `str(e)` in the log only:
```python
logger.exception("tool %s failed for user=%s: %s", tool_name, user, e)
return {"success": False, "message": f"Internal error in {tool_name}."}
```

## Info

### IN-01: `RATE_LIMIT_MESSAGE` hardcodes the policy numbers

**File:** `src/kb_mcp/rate_limit.py:19-24`
**Issue:** `RATE_LIMIT_WINDOW = 60` / `RATE_LIMIT_MAX = 30` are constants, but
the message string repeats `"30 requests per 60 seconds"` literally. Changing
the policy without updating the string (or vice versa) silently desynchronizes
the client-facing contract D-14 pins down.
**Fix:** `RATE_LIMIT_MESSAGE = (f"Rate limit exceeded: {RATE_LIMIT_MAX} requests per {RATE_LIMIT_WINDOW} seconds. Retry after the window.")`

### IN-02: Silent `except Exception: pass` swallows in `get_request_token`

**File:** `src/kb_mcp/server.py:81-92`, `109-110`, `125-126`
**Issue:** Five bare swallows (including around the `fastmcp` imports, so a
missing/broken FastMCP install degrades to "deny everything" with no log
line). Fail-closed outcome is correct, but diagnosability is zero — a
misconfigured deployment looks identical to an attack.
**Fix:** Log at `debug`/`warning` inside each handler before `pass`.

### IN-03: Coupling to FastMCP private internals

**File:** `src/kb_mcp/server.py:96`
**Issue:** `from fastmcp.server.context import _current_context` imports a
private (underscore) API; a minor FastMCP upgrade (`>=4,<5` allows any 4.x)
can break header extraction at runtime with no static signal.
**Fix:** Pin a tighter FastMCP range or add a startup self-test asserting the
import surface, with a loud error when it disappears.

### IN-04: Undeclared direct dependency + stale package metadata

**File:** `pyproject.toml:10-16` and `src/kb_mcp/cli.py:10-11`
**Issue:** `cli.py` imports `rich.console`/`rich.table` directly, but `rich`
appears nowhere in `dependencies` — it arrives only transitively via `typer`.
A future typer release dropping the transitive dep breaks `kb-mcp-tokens`
imports. Separately, `description = "Knowledge Base MCP Server - Storage
Layer"` is stale (this is now the full MCP server, not the storage layer).
**Fix:** Add `"rich>=13.0"` to `dependencies`; update the description.

### IN-05: Secrecy test overclaims — success path with a valid token is untested

**File:** `tests/test_server_auth.py:121-128`
**Issue:** `test_raw_token_never_reaches_logs_or_audit` uses a *bogus* token
(never added to the store), so both calls exercise only the denial path. A
valid token's success path (write logging in `log_write`, the
`logger.exception` path in `_invoke`) is never checked for secret leakage —
the test name promises "never" but proves "not on denial".
**Fix:** Add a valid-token variant: create with a real writer token, assert
the raw secret appears in neither the audit file nor captured logs.

### IN-06: Reads carry no user attribution in logs

**File:** `src/kb_mcp/server.py:175` and `src/kb_mcp/audit.py:66-68`
**Issue:** `log_read(tool)` records only the tool name — the verified `user`
available in `_invoke` is discarded. Per-spec (D-16 reads-light), but it
leaves read forensics unattributable; correlating a leaked-note incident to a
token owner requires cross-referencing elsewhere.
**Fix:** Consider `log_read(tool, user)` while keeping payloads out of the log.

### IN-07: Empty-key test omits `None`

**File:** `tests/test_rate_limit_audit.py:45-53`
**Issue:** `check_rate_limit` explicitly rejects `None` (`rate_limit.py:44`),
but the test parametrizes only `""` and `"   "`. The `None` branch — the one
closest to the real anonymous-caller path — is uncovered.
**Fix:** Add `None` to the bad-key cases.

### IN-08: Rate-limiter store has no synchronization

**File:** `src/kb_mcp/rate_limit.py:26`, `47-52`
**Issue:** The module dict is mutated without a lock. Under asyncio-only
serving the synchronous check-and-append is atomic enough, but a threaded
server (uvicorn workers/threads) can interleave two checks so both see
`len < 30` and both append — slightly overshooting the window. Single-process
personal-KB scale makes this negligible, recorded for completeness.
**Fix:** Guard with a `threading.Lock` if threaded serving is ever adopted.

---

_Reviewed: 2026-10-10T00:00:00Z_
_Reviewer: OpenCode (gsd-code-reviewer)_
_Depth: standard_
