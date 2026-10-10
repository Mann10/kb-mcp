"""Per-owner in-memory sliding-window rate limiter (D-11..D-14).

Transport-agnostic: no server imports, stdlib only. Pure module so Plan 09-03
can wire it into the transport layer without coupling.

Policy (locked decisions):
- D-11: keyed per token-owner (username from the verified token), never IP.
- D-12: 30 requests per 60 s sliding window (reference numbers kept verbatim).
- D-13: in-memory ephemeral dict; single-process personal KB needs no
  multi-process coordination, no persistence, no threads.
- D-14: denied clients get RATE_LIMIT_MESSAGE (contains "Rate limit" + "60").

No rotation is performed in this phase by design — the store is intentionally
ephemeral and resets on process restart.
"""

import time

RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 30

RATE_LIMIT_MESSAGE = (
    "Rate limit exceeded: 30 requests per 60 seconds. Retry after the window."
)

_store: dict[str, list[float]] = {}


def owner_key(entry) -> str:
    """Derive the limiter bucket from a verified token entry (D-11).

    Single choke point so Plan 09-03 cannot key on IP by accident.
    """
    return entry.username


def check_rate_limit(user: str, now: float | None = None) -> bool:
    """Return True if the request is allowed, False when the window is exhausted.

    ``now`` is injectable for deterministic tests; defaults to ``time.time()``.
    Empty/whitespace keys raise ValueError (fail-closed: anonymous callers are
    never bucketed together).
    """
    if user is None or not str(user).strip():
        raise ValueError("rate-limit key must be a non-empty user")
    timestamp = time.time() if now is None else now
    requests = _store.setdefault(user, [])
    requests[:] = [t for t in requests if timestamp - t < RATE_LIMIT_WINDOW]
    if len(requests) >= RATE_LIMIT_MAX:
        return False
    requests.append(timestamp)
    return True


def reset_rate_limits() -> None:
    """Clear all buckets (test isolation + single-process reset hook)."""
    _store.clear()
