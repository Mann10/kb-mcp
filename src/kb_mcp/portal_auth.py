"""Portal BFF auth seam (Phase 10-01).

Server-side Supabase JWT validation + user/admin gates for the portal BFF.
Fail-closed on every path; never trusts client-sent user ids; privileged
service_role key never leaves the server.

Import-safe: zero I/O and zero required env at import. All env reads happen
per-request inside handlers.
"""

import logging
import os

from pydantic import BaseModel

logger = logging.getLogger(__name__)

PORTAL_INVALID_MESSAGE = "Invalid or missing login. Please log in again."
PORTAL_FORBIDDEN_MESSAGE = "Admin access required. Contact the owner for approval."

# Process-lifetime cache of stateless Supabase clients, keyed on (url, key).
# Populated only from _supabase_client(); empty at import time.
_client_cache: dict[tuple[str, str], object] = {}


class PortalUser(BaseModel):
    """Authenticated portal user derived from a verified Supabase JWT."""

    id: str
    email: str
    is_admin: bool = False


def mask_email(email: str | None) -> str:
    """Mask an email for log output (secrecy choke point, mirrors audit.mask_token)."""
    if not email:
        return "missing"
    if len(email) < 8:
        return "****"
    return f"{email[:3]}...{email[-4:]}"


def _mask_token_tail(raw: str | None) -> str:
    """Mask a raw JWT for log output; never log the full secret."""
    try:
        from kb_mcp.audit import mask_token
    except Exception:
        if not raw:
            return "missing"
        if len(raw) >= 8:
            return f"{raw[:4]}...{raw[-4:]}"
        return "****"
    try:
        return mask_token(raw)
    except Exception:
        return "missing"


def is_admin_email(email: str | None) -> bool:
    """True when email matches ADMIN_EMAILS allowlist (case-insensitive, stripped)."""
    if not email or not email.strip():
        return False
    raw = os.environ.get("ADMIN_EMAILS", "")
    if not raw.strip():
        return False
    wanted = email.strip().lower()
    for candidate in raw.split(","):
        if candidate.strip().lower() == wanted:
            return True
    return False


def _claims_to_user(claims: object) -> PortalUser | None:
    """Normalize get_claims/get_user payloads into a PortalUser. Returns None if unusable."""
    if claims is None:
        return None
    data: dict = {}
    # ClaimsResponse object shapes: .claims attr, or dict with claims key, or flat dict
    if isinstance(claims, dict):
        if isinstance(claims.get("claims"), dict):
            data = claims["claims"]
        elif isinstance(claims.get("user"), dict):
            data = claims["user"]
        else:
            data = claims
    else:
        inner = getattr(claims, "claims", None)
        if isinstance(inner, dict):
            data = inner
        else:
            user_obj = getattr(claims, "user", None)
            if user_obj is not None:
                return _claims_to_user(user_obj)
            # Supabase User object: id/email/app_metadata attrs
            try:
                data = {
                    "sub": getattr(claims, "id", None),
                    "email": getattr(claims, "email", None),
                    "app_metadata": getattr(claims, "app_metadata", None) or {},
                }
            except Exception:
                return None
    sub = data.get("sub") or data.get("id")
    email = data.get("email") or ""
    app_meta = data.get("app_metadata") or data.get("appMetadata") or {}
    if not isinstance(app_meta, dict):
        app_meta = {}
    is_admin = bool(app_meta.get("is_admin") is True)
    if not sub or not isinstance(sub, str):
        return None
    if not email or not isinstance(email, str):
        return None
    return PortalUser(id=sub, email=email, is_admin=is_admin)


def _reset_client_cache() -> None:
    """Test seam: forget every cached Supabase client."""
    _client_cache.clear()


def _supabase_client(url: str, key: str):
    """Cached ``create_client(url, key)``, keyed on the exact ``(url, key)`` pair.

    Reusing the client keeps its JWKS cache warm between requests instead of
    forcing a network fetch to Supabase Auth on every portal API call. Both
    components of the key matter: keying on url alone would hand the
    ``service_role`` client created by :func:`ensure_admin_bootstrap` to an
    anon-key lookup, or keep a stale client alive after anon-key rotation.

    The ``from supabase import create_client`` import stays INSIDE the
    function and the cache is never populated at module scope, preserving
    import-safety (zero I/O, zero required env at import). The cache holds
    stateless clients only — never a signed-in user session.

    No TTL, LRU, or eviction: keys rotate only on deploy and the whole cache
    is cleared by :func:`_reset_client_cache` in tests.
    """
    cache_key = (url, key)
    client = _client_cache.get(cache_key)
    if client is not None:
        return client
    try:
        from supabase import create_client  # type: ignore
    except Exception as e:
        raise RuntimeError(f"supabase client unavailable: {e}")
    client = create_client(url, key)
    _client_cache[cache_key] = client
    return client


def _supabase_get_claims(token: str) -> object:
    """Primary offline JWT verification via supabase.auth.get_claims(token).

    Reads SUPABASE_URL + SUPABASE_ANON_KEY per call (env is never cached);
    only the constructed client is. Raises on ANY failure so the caller can
    fall back / deny fail-closed.
    """
    url = os.environ.get("SUPABASE_URL", "").strip()
    anon = os.environ.get("SUPABASE_ANON_KEY", "").strip()
    if not url or not anon:
        raise RuntimeError("Missing SUPABASE_URL / SUPABASE_ANON_KEY")
    client = _supabase_client(url, anon)
    # supabase-py: client.auth.get_claims(jwt)
    get_claims = getattr(client.auth, "get_claims", None)
    if get_claims is None:
        raise RuntimeError("supabase client has no auth.get_claims")
    return get_claims(token)


def _supabase_get_user(token: str) -> object:
    """Fallback server-side check via supabase.auth.get_user(token)."""
    url = os.environ.get("SUPABASE_URL", "").strip()
    anon = os.environ.get("SUPABASE_ANON_KEY", "").strip()
    if not url or not anon:
        raise RuntimeError("Missing SUPABASE_URL / SUPABASE_ANON_KEY")
    client = _supabase_client(url, anon)
    get_user = getattr(client.auth, "get_user", None)
    if get_user is None:
        raise RuntimeError("supabase client has no auth.get_user")
    return get_user(token)


def validate_portal_jwt(raw: str | None) -> PortalUser | None:
    """Validate a Supabase JWT server-side, fail-closed.

    Primary path: supabase.auth.get_claims (offline JWKS). Fallback:
    supabase.auth.get_user (HS256 legacy / server check). Returns None on
    missing/blank/any exception. Never accepts a client-sent user id —
    no such parameter exists by construction.
    """
    if raw is None or not raw.strip():
        return None
    token = raw.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        return None
    # Primary: offline claims verification
    try:
        claims = _supabase_get_claims(token)
        user = _claims_to_user(claims)
        if user is not None:
            return user
        raise ValueError("Unusable claims payload")
    except Exception as e:
        logger.warning(
            "portal jwt claims check failed: token=%s (%s)",
            _mask_token_tail(token),
            type(e).__name__,
        )
    # Fallback: server-side user lookup (HS256 legacy instances)
    try:
        user_resp = _supabase_get_user(token)
        user = _claims_to_user(user_resp)
        if user is not None:
            return user
        logger.warning("portal jwt user check returned unusable payload")
        return None
    except Exception as e:
        logger.warning(
            "portal jwt validation failed: token=%s (%s)",
            _mask_token_tail(token),
            type(e).__name__,
        )
        return None


def ensure_admin_bootstrap(user: PortalUser) -> bool:
    """Grant is_admin via service_role when email is in ADMIN_EMAILS.

    Returns True when the bootstrap write succeeded (caller treats user as
    admin for this request). Any failure returns False fail-closed with no
    exception to the caller. Logs only masked email prefix...suffix.
    """
    try:
        if user.is_admin:
            return False
        if not is_admin_email(user.email):
            return False
        url = os.environ.get("SUPABASE_URL", "").strip()
        service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not url or not service_key:
            logger.warning(
                "admin bootstrap skipped (missing server env) for %s",
                mask_email(user.email),
            )
            return False
        try:
            client = _supabase_client(url, service_key)
        except Exception as e:
            logger.warning("admin bootstrap unavailable (no supabase client): %s", e)
            return False
        admin_api = getattr(getattr(client, "auth", None), "admin", None)
        if admin_api is None or not hasattr(admin_api, "update_user_by_id"):
            logger.warning("admin bootstrap unavailable (no auth.admin API)")
            return False
        admin_api.update_user_by_id(user.id, {"app_metadata": {"is_admin": True}})
        logger.info("admin bootstrap granted for %s", mask_email(user.email))
        return True
    except Exception as e:
        logger.warning(
            "admin bootstrap failed for %s (%s)",
            mask_email(user.email),
            type(e).__name__,
        )
        return False


def _bearer_from_request(request: object) -> str | None:
    """Extract Bearer JWT from a Starlette Request (Authorization header)."""
    try:
        headers = getattr(request, "headers", None)
        if headers is None:
            return None
        auth = headers.get("authorization")
        if auth is None:
            # case-insensitive scan for non-standard header dicts
            try:
                for name, value in headers.items():
                    if name.lower() == "authorization" and value:
                        auth = value
                        break
            except Exception:
                return None
        if not auth:
            return None
        scheme, _, cred = auth.partition(" ")
        if scheme.lower() != "bearer" or not cred.strip():
            return None
        return cred.strip()
    except Exception:
        return None


def require_user(request: object) -> PortalUser | None:
    """Gate: valid JWT in Authorization header → PortalUser, else None."""
    token = _bearer_from_request(request)
    if not token:
        return None
    return validate_portal_jwt(token)


def require_admin(request: object) -> PortalUser | None:
    """Gate: require_user + (is_admin or ADMIN_EMAILS bootstrap), else None."""
    user = require_user(request)
    if user is None:
        return None
    if user.is_admin:
        return user
    try:
        if ensure_admin_bootstrap(user):
            user.is_admin = True
            return user
    except Exception:
        return None
    return None
