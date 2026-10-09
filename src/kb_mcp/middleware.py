"""Transport-agnostic token enforcement for every tool call (AUTH-02).

Plan 01 built WHAT a token is; this module builds HOW every call is
checked: verify on every invocation, scope-check, then invoke. Gated
tools declare ``token`` as a keyword parameter (keyword-or-positional-last)
and ``_store`` for store injection; the decorators key on the ``token``
keyword only so positional tool arguments are never misinterpreted.

No transport-SDK imports here — Phase 9 adapts these decorators to
the transport layer without changing them.
"""

import functools
import logging
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from .auth import TokenEntry, TokenStore
from .errors import AuthenticationError, AuthorizationError

logger = logging.getLogger(__name__)

READ_SCOPE = "notes:read"
WRITE_SCOPE = "notes:write"

INVALID_TOKEN_MESSAGE = "Invalid or missing token."
READ_DENIED_MESSAGE = "Read access required. Use a valid token or contact the owner."
WRITE_DENIED_MESSAGE = "Write access required. Use a write token or contact the owner."

_default_store: TokenStore | None = None


def configure_default_store(store: TokenStore | None) -> None:
    """Set the module-level default store used when ``_store`` is omitted."""
    global _default_store
    _default_store = store


def verify_token(token: str | None, store: TokenStore) -> TokenEntry | None:
    """Verify a raw token against the store on every call (fail-closed).

    Returns the entry on success, else None. Never raises — all failure
    surfaces become None so decorators can deny uniformly. None/empty/
    whitespace-only input short-circuits without touching the store.
    """
    if token is None or not token.strip():
        return None
    entry = store.lookup(token)
    if entry is None:
        logger.warning("auth denied: unknown token")
        return None
    store.update_last_used(token)
    return entry


P = ParamSpec("P")
R = TypeVar("R")


def _gate(
    fn: Callable[P, R], required_scope: str, denied_message: str
) -> Callable[P, R]:
    """Wrap a tool so verification runs verify -> scope-check -> invoke."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, token: str | None = None, _store: TokenStore | None = None, **kwargs: P.kwargs) -> R:
        store = _store if _store is not None else _default_store
        if store is None:
            raise AuthenticationError(INVALID_TOKEN_MESSAGE)
        entry = verify_token(token, store)
        if entry is None:
            raise AuthenticationError(INVALID_TOKEN_MESSAGE)
        if required_scope not in entry.scopes:
            logger.warning(
                "auth denied: insufficient scope for %s...%s (user=%s)",
                entry.key_prefix,
                entry.key_suffix,
                entry.username,
            )
            raise AuthorizationError(denied_message)
        return fn(*args, token=token, _store=store, **kwargs)  # type: ignore[call-arg]

    return wrapper  # type: ignore[return-value]


def require_read(fn: Callable[P, R]) -> Callable[P, R]:
    """Gate a tool behind the ``notes:read`` scope.

    The wrapped tool must declare ``token`` as a keyword-or-positional-last
    parameter (``token`` is extracted by keyword only) and may declare
    ``_store`` to receive the resolved store.
    """
    return _gate(fn, READ_SCOPE, READ_DENIED_MESSAGE)


def require_write(fn: Callable[P, R]) -> Callable[P, R]:
    """Gate a tool behind the ``notes:write`` scope.

    The wrapped tool must declare ``token`` as a keyword-or-positional-last
    parameter (``token`` is extracted by keyword only) and may declare
    ``_store`` to receive the resolved store.
    """
    return _gate(fn, WRITE_SCOPE, WRITE_DENIED_MESSAGE)
