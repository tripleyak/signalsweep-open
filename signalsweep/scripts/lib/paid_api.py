"""Shared HTTP client for paid / authenticated APIs (signalsweep 3.7+).

All 10 paid-API sources in the 3.7 bundle use this helper instead of rolling
their own HTTP. Mirrors `public_api.py` API surface with auth-aware additions:

- `fetch_json(url, auth=..., ...)` — GET + parse JSON, returns `{"items", "error"}` envelope.
- `fetch_xml(url, auth=..., ...)` — GET + parse XML, same envelope.
- `post_json(url, data, auth=..., ...)` — POST JSON body + parse JSON response.
- Auth variants via `AuthSpec`: bearer, header, query_param.
- 401/403 → `credentials_invalid` (no retry; distinct from `rate_limited`).
- 429/503 Retry-After honored (one retry, capped at 60s).
- ETag / If-None-Match caching via `cache_key` parameter (reuses `lib.cache`).
- `is_paid_apis_enabled(config)` — honors `SIGNALSWEEP_DISABLE_PAID_APIS` toggle.

None of the functions raise. Callers get a dict they can inspect for `error`
before proceeding to `items`.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Literal

from . import cache as _cache_module


VERSION = "3.7"
USER_AGENT_BASE = f"signalsweep/{VERSION} (+https://github.com/tripleyak/signalsweep)"
RETRY_AFTER_CAP_SECONDS = 60
DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_CACHE_TTL_HOURS = 24


AuthType = Literal["bearer", "header", "query_param"]


@dataclass(frozen=True)
class AuthSpec:
    """How to attach credentials to a request.

    - `bearer`: Adds `Authorization: Bearer <value>` header. `name` ignored.
    - `header`: Adds `<name>: <value>` header (e.g., `x-api-key`).
    - `query_param`: Appends `?<name>=<value>` to URL.
    """

    type: AuthType
    value: str
    name: str = ""  # header/query param name; ignored for bearer

    def is_valid(self) -> bool:
        if not self.value:
            return False
        if self.type in ("header", "query_param") and not self.name:
            return False
        return True


def is_paid_apis_enabled(config: dict[str, Any]) -> bool:
    """Return False if SIGNALSWEEP_DISABLE_PAID_APIS is truthy, else True.

    Truthy values: "1", "true", "yes" (case-insensitive).
    """
    value = str(config.get("SIGNALSWEEP_DISABLE_PAID_APIS", "")).strip().lower()
    return value not in {"1", "true", "yes"}


def _apply_auth_to_url(url: str, auth: AuthSpec | None) -> str:
    if auth and auth.type == "query_param" and auth.is_valid():
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}{urllib.parse.urlencode({auth.name: auth.value})}"
    return url


def _apply_auth_to_headers(headers: dict[str, str], auth: AuthSpec | None) -> dict[str, str]:
    if not auth or not auth.is_valid():
        return headers
    if auth.type == "bearer":
        headers["Authorization"] = f"Bearer {auth.value}"
    elif auth.type == "header":
        headers[auth.name] = auth.value
    return headers


def _build_url(url: str, params: dict[str, Any] | None) -> str:
    if not params:
        return url
    qs = urllib.parse.urlencode(params, doseq=True)
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{qs}"


def _build_headers(
    user_agent_suffix: str,
    etag: str | None,
    extra: dict[str, str] | None,
    auth: AuthSpec | None,
) -> dict[str, str]:
    ua = USER_AGENT_BASE
    if user_agent_suffix:
        ua = f"{ua} {user_agent_suffix}"
    headers = {"User-Agent": ua}
    if etag:
        headers["If-None-Match"] = etag
    if extra:
        headers.update(extra)
    headers = _apply_auth_to_headers(headers, auth)
    return headers


def _read_cache_entry(cache_key: str | None, cache_ttl_hours: int) -> dict[str, Any] | None:
    if not cache_key:
        return None
    try:
        return _cache_module.load_cache(cache_key, ttl_hours=cache_ttl_hours)
    except Exception:
        return None


def _write_cache_entry(cache_key: str | None, etag: str | None, body: Any) -> None:
    if not cache_key:
        return
    try:
        _cache_module.save_cache(cache_key, {"etag": etag, "body": body})
    except Exception:
        pass  # cache writes are best-effort


def _retry_after_seconds(err: urllib.error.HTTPError) -> int:
    raw = err.headers.get("Retry-After") if err.headers else None
    try:
        seconds = int(raw) if raw is not None else 1
    except (TypeError, ValueError):
        seconds = 1
    return min(max(seconds, 0), RETRY_AFTER_CAP_SECONDS)


def _perform_request(
    url: str,
    headers: dict[str, str],
    method: str,
    body: bytes | None,
    timeout: int,
) -> tuple[int, bytes, dict[str, str]]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        resp_body = resp.read()
        resp_headers = dict(resp.headers) if hasattr(resp, "headers") else {}
        status = resp.getcode() if hasattr(resp, "getcode") else 200
        return status, resp_body, resp_headers


def _fetch_raw(
    url: str,
    *,
    method: str,
    body: bytes | None,
    params: dict[str, Any] | None,
    auth: AuthSpec | None,
    cache_key: str | None,
    cache_ttl_hours: int,
    user_agent_suffix: str,
    extra_headers: dict[str, str] | None,
    timeout: int,
) -> dict[str, Any]:
    """Core HTTP logic with auth + ETag cache + retry. Returns envelope with raw body bytes."""
    url_with_params = _build_url(url, params)
    final_url = _apply_auth_to_url(url_with_params, auth)
    cached = _read_cache_entry(cache_key, cache_ttl_hours) if method == "GET" else None
    etag = cached.get("etag") if cached else None

    headers = _build_headers(user_agent_suffix, etag, extra_headers, auth)

    def _try_once() -> dict[str, Any]:
        try:
            status, resp_body, resp_headers = _perform_request(final_url, headers, method, body, timeout)
            new_etag = resp_headers.get("ETag") or resp_headers.get("Etag")
            return {"status": status, "body": resp_body, "etag": new_etag, "error": None}
        except urllib.error.HTTPError as err:
            if err.code == 304 and cached is not None:
                return {"status": 304, "body": None, "etag": etag, "error": None, "_use_cached": True}
            if err.code == 404:
                return {"status": 404, "body": None, "etag": None, "error": "not_found"}
            if err.code in (401, 403):
                return {"status": err.code, "body": None, "etag": None, "error": "credentials_invalid"}
            if err.code in (429, 503):
                return {
                    "status": err.code,
                    "body": None,
                    "etag": None,
                    "error": "rate_limited",
                    "_retry_after": _retry_after_seconds(err),
                }
            return {"status": err.code, "body": None, "etag": None, "error": f"http_{err.code}"}
        except socket.timeout:
            return {"status": 0, "body": None, "etag": None, "error": "network_timeout"}
        except urllib.error.URLError as err:
            reason = str(getattr(err, "reason", err))
            if "timed out" in reason.lower():
                return {"status": 0, "body": None, "etag": None, "error": "network_timeout"}
            return {"status": 0, "body": None, "etag": None, "error": f"network_error: {reason}"}
        except Exception as err:  # defensive catch-all
            return {"status": 0, "body": None, "etag": None, "error": f"unexpected: {type(err).__name__}"}

    result = _try_once()
    # One retry on rate_limited only — credentials_invalid never retries.
    if result.get("error") == "rate_limited":
        time.sleep(result.get("_retry_after", 1))
        result = _try_once()

    return result


def fetch_json(
    url: str,
    *,
    auth: AuthSpec | None = None,
    params: dict[str, Any] | None = None,
    cache_key: str | None = None,
    cache_ttl_hours: int = DEFAULT_CACHE_TTL_HOURS,
    user_agent_suffix: str = "",
    extra_headers: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """GET + parse JSON. Returns {"items": <parsed>, "error": None|str}. Never raises."""
    raw = _fetch_raw(
        url,
        method="GET",
        body=None,
        params=params,
        auth=auth,
        cache_key=cache_key,
        cache_ttl_hours=cache_ttl_hours,
        user_agent_suffix=user_agent_suffix,
        extra_headers=extra_headers,
        timeout=timeout,
    )

    if raw.get("_use_cached"):
        cached = _read_cache_entry(cache_key, cache_ttl_hours)
        return {"items": cached.get("body") if cached else None, "error": None}

    if raw.get("error"):
        return {"items": None, "error": raw["error"]}

    body = raw.get("body") or b""
    try:
        parsed = json.loads(body.decode("utf-8")) if body else None
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        return {"items": None, "error": f"parse_error: {err}"}

    _write_cache_entry(cache_key, raw.get("etag"), parsed)
    return {"items": parsed, "error": None}


def fetch_xml(
    url: str,
    *,
    auth: AuthSpec | None = None,
    params: dict[str, Any] | None = None,
    cache_ttl_hours: int = DEFAULT_CACHE_TTL_HOURS,
    user_agent_suffix: str = "",
    extra_headers: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """GET + parse XML. Returns {"items": <ElementTree root>, "error": None|str}. Never raises."""
    raw = _fetch_raw(
        url,
        method="GET",
        body=None,
        params=params,
        auth=auth,
        cache_key=None,  # skip cache for XML (parity with public_api.py)
        cache_ttl_hours=cache_ttl_hours,
        user_agent_suffix=user_agent_suffix,
        extra_headers=extra_headers,
        timeout=timeout,
    )

    if raw.get("error"):
        return {"items": None, "error": raw["error"]}

    body = raw.get("body") or b""
    try:
        root = ET.fromstring(body.decode("utf-8")) if body else None
    except (UnicodeDecodeError, ET.ParseError) as err:
        return {"items": None, "error": f"parse_error: {err}"}

    return {"items": root, "error": None}


def post_json(
    url: str,
    data: dict[str, Any],
    *,
    auth: AuthSpec | None = None,
    user_agent_suffix: str = "",
    extra_headers: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """POST JSON body + parse JSON response. Returns {"items", "error"} envelope.

    No caching for POST (request-specific bodies). 401/403 surface as
    `credentials_invalid`; 429 retried once with Retry-After.
    """
    headers = {"Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    body_bytes = json.dumps(data).encode("utf-8")

    raw = _fetch_raw(
        url,
        method="POST",
        body=body_bytes,
        params=None,
        auth=auth,
        cache_key=None,
        cache_ttl_hours=0,
        user_agent_suffix=user_agent_suffix,
        extra_headers=headers,
        timeout=timeout,
    )

    if raw.get("error"):
        return {"items": None, "error": raw["error"]}

    resp_body = raw.get("body") or b""
    try:
        parsed = json.loads(resp_body.decode("utf-8")) if resp_body else None
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        return {"items": None, "error": f"parse_error: {err}"}

    return {"items": parsed, "error": None}
