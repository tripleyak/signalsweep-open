"""Login-with-Amazon (LWA) OAuth refresh-token helper for SP-API + Ads API.

Both Amazon APIs share the same LWA OAuth flow:

1. Register an app in Seller Central / Ads Console → get client_id + client_secret.
2. Authorize the app via OAuth consent → get a long-lived refresh_token.
3. Exchange refresh_token for a short-lived access_token (~1h TTL) on each burst.

This module owns step 3 and caches the access token in-process with a 5-minute
expiry buffer. Never persists tokens to disk — process-local only.

Never raises. Failures return `(None, 0)` with an error string in a module-level
last-error slot for diagnostics.
"""

from __future__ import annotations

import hashlib
import time
import urllib.parse
from typing import Any

from . import paid_api

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
EXPIRY_BUFFER_SECONDS = 300  # 5-minute buffer before real expiry
DEFAULT_TOKEN_TTL_SECONDS = 3600  # Amazon LWA default is 1h; overridden by response

# Process-local token cache keyed by sha256(refresh_token).
# Structure: {cache_key: (access_token, expires_at_epoch)}
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_LAST_ERROR: dict[str, str] = {}


def _cache_key(refresh_token: str) -> str:
    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()[:32]


def _is_fresh(expires_at: float) -> bool:
    """True if token has at least EXPIRY_BUFFER_SECONDS remaining."""
    return expires_at > (time.time() + EXPIRY_BUFFER_SECONDS)


def get_lwa_access_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    *,
    force_refresh: bool = False,
) -> tuple[str | None, float]:
    """Exchange an LWA refresh token for an access token.

    Returns:
        `(access_token, expires_at_epoch)` on success.
        `(None, 0.0)` on failure — check `get_last_error()` for reason.

    In-process cache: subsequent calls within the token's expiry buffer return
    the cached token without a network round-trip.
    """
    if not (refresh_token and client_id and client_secret):
        _LAST_ERROR["reason"] = "missing_credentials"
        return None, 0.0

    key = _cache_key(refresh_token)

    if not force_refresh:
        cached = _TOKEN_CACHE.get(key)
        if cached and _is_fresh(cached[1]):
            return cached

    # POST form-encoded to LWA token endpoint. This is not JSON.
    form = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")

    raw = paid_api._fetch_raw(
        LWA_TOKEN_URL,
        method="POST",
        body=form,
        params=None,
        auth=None,
        cache_key=None,
        cache_ttl_hours=0,
        user_agent_suffix="(lwa-auth)",
        extra_headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )

    if raw.get("error"):
        _LAST_ERROR["reason"] = raw["error"]
        return None, 0.0

    body = raw.get("body") or b""
    try:
        import json
        payload: dict[str, Any] = json.loads(body.decode("utf-8")) if body else {}
    except (UnicodeDecodeError, ValueError) as err:
        _LAST_ERROR["reason"] = f"parse_error: {err}"
        return None, 0.0

    access_token = payload.get("access_token")
    expires_in = payload.get("expires_in", DEFAULT_TOKEN_TTL_SECONDS)
    if not access_token:
        _LAST_ERROR["reason"] = f"no_access_token_in_response: keys={list(payload.keys())}"
        return None, 0.0

    try:
        expires_at = time.time() + float(expires_in)
    except (TypeError, ValueError):
        expires_at = time.time() + DEFAULT_TOKEN_TTL_SECONDS

    _TOKEN_CACHE[key] = (access_token, expires_at)
    _LAST_ERROR.pop("reason", None)
    return access_token, expires_at


def get_last_error() -> str | None:
    """Return the reason string from the most recent failed `get_lwa_access_token` call."""
    return _LAST_ERROR.get("reason")


def clear_cache() -> None:
    """Drop all cached LWA tokens. Used by tests; rarely needed at runtime."""
    _TOKEN_CACHE.clear()
    _LAST_ERROR.clear()
