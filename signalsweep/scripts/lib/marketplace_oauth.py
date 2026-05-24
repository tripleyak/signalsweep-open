"""OAuth 2.0 helper for v3.14+ non-Amazon marketplace adapters.

Generalizes `amazon_auth.py`'s LWA pattern for vendor-agnostic OAuth 2.0:

- **Client credentials flow** (service-to-service): POST `grant_type=client_credentials`
  to vendor token URL; used by Walmart Marketplace / Walmart Connect.
- **Refresh token flow** (user-authorized): POST `grant_type=refresh_token` with
  a long-lived refresh_token; used by Etsy, Pinterest, TikTok Shop Partner.

Process-local token cache keyed by (vendor, client_id). 5-minute expiry buffer.
Never persists tokens to disk.

Never raises. Failures return `(None, 0.0)` with a module-level last-error slot
for diagnostics. Call `get_last_error(vendor)` to inspect.

Consumers:
  - etsy.py
  - pinterest_commerce.py
  - walmart_marketplace.py
  - walmart_connect.py
  - tiktok_shop_seller.py

`amazon_vendor.py` uses `amazon_auth.py` directly since its flow is identical
to SP-API LWA.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
from typing import Any, Literal

from . import paid_api


EXPIRY_BUFFER_SECONDS = 300
DEFAULT_TOKEN_TTL_SECONDS = 3600


GrantType = Literal["client_credentials", "refresh_token"]


# Process-local token cache keyed by (vendor, client_id_hash).
_TOKEN_CACHE: dict[tuple[str, str], tuple[str, float]] = {}
_LAST_ERROR: dict[str, str] = {}


def _cache_key(vendor: str, client_id: str) -> tuple[str, str]:
    cid_hash = hashlib.sha256(client_id.encode("utf-8")).hexdigest()[:16]
    return (vendor, cid_hash)


def _is_fresh(expires_at: float) -> bool:
    return expires_at > (time.time() + EXPIRY_BUFFER_SECONDS)


def get_access_token(
    vendor: str,
    token_url: str,
    client_id: str,
    client_secret: str,
    *,
    grant_type: GrantType = "client_credentials",
    refresh_token: str = "",
    scope: str = "",
    extra_params: dict[str, str] | None = None,
    force_refresh: bool = False,
) -> tuple[str | None, float]:
    """Exchange credentials for an OAuth access token.

    Args:
        vendor: Short vendor identifier for cache keying + error reporting (e.g.
            ``"etsy"``, ``"walmart_marketplace"``).
        token_url: Vendor-specific OAuth token endpoint.
        client_id / client_secret: App credentials.
        grant_type: ``client_credentials`` (service-to-service) or
            ``refresh_token`` (user-authorized long-lived refresh token).
        refresh_token: Required when ``grant_type == "refresh_token"``.
        scope: Optional scope string (space-separated). Some vendors require.
        extra_params: Vendor-specific body params (e.g. Etsy's ``"include_granted_scopes"``).
        force_refresh: Bypass cache; fetch a fresh token.

    Returns:
        ``(access_token, expires_at_epoch)`` on success, ``(None, 0.0)`` on failure.
    """
    if not (client_id and client_secret and token_url):
        _LAST_ERROR[vendor] = "missing_credentials"
        return None, 0.0
    if grant_type == "refresh_token" and not refresh_token:
        _LAST_ERROR[vendor] = "missing_refresh_token"
        return None, 0.0

    key = _cache_key(vendor, client_id)

    if not force_refresh:
        cached = _TOKEN_CACHE.get(key)
        if cached and _is_fresh(cached[1]):
            return cached

    body: dict[str, str] = {
        "grant_type": grant_type,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if grant_type == "refresh_token":
        body["refresh_token"] = refresh_token
    if scope:
        body["scope"] = scope
    if extra_params:
        body.update(extra_params)

    encoded = urllib.parse.urlencode(body).encode("utf-8")

    raw = paid_api._fetch_raw(
        token_url,
        method="POST",
        body=encoded,
        params=None,
        auth=None,
        cache_key=None,
        cache_ttl_hours=0,
        user_agent_suffix=f"(marketplace_oauth-{vendor})",
        extra_headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )

    err = raw.get("error")
    if err:
        _LAST_ERROR[vendor] = err
        return None, 0.0

    raw_body = raw.get("body") or b""
    try:
        payload: dict[str, Any] = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except (UnicodeDecodeError, ValueError) as exc:
        _LAST_ERROR[vendor] = f"parse_error: {exc}"
        return None, 0.0

    access_token = payload.get("access_token")
    expires_in = payload.get("expires_in", DEFAULT_TOKEN_TTL_SECONDS)
    if not access_token or not isinstance(access_token, str):
        _LAST_ERROR[vendor] = f"no_access_token_in_response: keys={list(payload.keys())}"
        return None, 0.0

    try:
        expires_at = time.time() + float(expires_in)
    except (TypeError, ValueError):
        expires_at = time.time() + DEFAULT_TOKEN_TTL_SECONDS

    _TOKEN_CACHE[key] = (access_token, expires_at)
    _LAST_ERROR.pop(vendor, None)
    return access_token, expires_at


def fetch_with_bearer(
    url: str,
    vendor: str,
    token_url: str,
    client_id: str,
    client_secret: str,
    *,
    grant_type: GrantType = "client_credentials",
    refresh_token: str = "",
    scope: str = "",
    params: dict[str, Any] | None = None,
    cache_key: str | None = None,
    cache_ttl_hours: int = 24,
    extra_headers: dict[str, str] | None = None,
    user_agent_suffix: str = "",
) -> dict[str, Any]:
    """One-shot helper: acquire token, make GET with bearer, return `{items, error}` envelope.

    Retries once on 401 by forcing a token refresh (handles stale-token edge case).
    Returns credentials_missing / credentials_invalid envelopes per error class.
    """
    if not (client_id and client_secret):
        return {"items": None, "error": "credentials_missing"}

    token, _expires_at = get_access_token(
        vendor, token_url, client_id, client_secret,
        grant_type=grant_type, refresh_token=refresh_token, scope=scope,
    )
    if not token:
        reason = get_last_error(vendor) or "credentials_invalid"
        # Token-endpoint 401/403 → credentials_invalid; other failures pass reason.
        if "401" in reason or "403" in reason or "invalid" in reason.lower():
            return {"items": None, "error": "credentials_invalid"}
        return {"items": None, "error": f"oauth_error: {reason}"}

    headers = dict(extra_headers or {})
    headers["Authorization"] = f"Bearer {token}"

    result = paid_api.fetch_json(
        url, auth=None, params=params,
        cache_key=cache_key, cache_ttl_hours=cache_ttl_hours,
        user_agent_suffix=user_agent_suffix or f"(marketplace_oauth-{vendor})",
        extra_headers=headers,
    )

    # 401 on data endpoint → try once more with a forced-refresh token.
    err = (result.get("error") or "") if isinstance(result.get("error"), str) else ""
    if "401" in err:
        token, _ = get_access_token(
            vendor, token_url, client_id, client_secret,
            grant_type=grant_type, refresh_token=refresh_token, scope=scope,
            force_refresh=True,
        )
        if not token:
            return {"items": None, "error": "credentials_invalid"}
        headers["Authorization"] = f"Bearer {token}"
        result = paid_api.fetch_json(
            url, auth=None, params=params,
            cache_key=cache_key, cache_ttl_hours=cache_ttl_hours,
            user_agent_suffix=user_agent_suffix or f"(marketplace_oauth-{vendor})",
            extra_headers=headers,
        )
        err2 = (result.get("error") or "") if isinstance(result.get("error"), str) else ""
        if "401" in err2 or "403" in err2:
            return {"items": None, "error": "credentials_invalid"}

    return result


def get_last_error(vendor: str) -> str | None:
    return _LAST_ERROR.get(vendor)


def clear_cache() -> None:
    """Drop all cached OAuth tokens. Used by tests."""
    _TOKEN_CACHE.clear()
    _LAST_ERROR.clear()
