"""Shared HTTP client for no-auth public APIs (signalsweep 3.6+).

All 13 public-data sources in the 3.6 bundle use this helper instead of rolling
their own HTTP. Provides:

- `fetch_json(url, ...)` — GET + parse JSON, returns `{"items", "error"}` envelope.
- `fetch_xml(url, ...)` — GET + parse XML (stdlib ElementTree), same envelope.
- ETag / If-None-Match caching via `cache_key` parameter (reuses `lib.cache`).
- Retry-After honoring on 429/503 (retries once, caps sleep at 60s).
- Consistent User-Agent: `signalsweep/3.6 (+https://github.com/tripleyak/signalsweep){suffix}`.
- `is_public_apis_enabled(config)` — honors `SIGNALSWEEP_DISABLE_PUBLIC_APIS` toggle.

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
from typing import Any

from . import cache as _cache_module


VERSION = "3.6"
USER_AGENT_BASE = f"signalsweep/{VERSION} (+https://github.com/tripleyak/signalsweep)"
RETRY_AFTER_CAP_SECONDS = 60
DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_CACHE_TTL_HOURS = 24


def is_public_apis_enabled(config: dict[str, Any]) -> bool:
    """Return False if SIGNALSWEEP_DISABLE_PUBLIC_APIS is truthy, else True.

    Truthy values: "1", "true", "yes" (case-insensitive).
    Any other value (including "0", "false", "", None) counts as enabled.
    """
    value = str(config.get("SIGNALSWEEP_DISABLE_PUBLIC_APIS", "")).strip().lower()
    return value not in {"1", "true", "yes"}


def _build_url(url: str, params: dict[str, Any] | None) -> str:
    if not params:
        return url
    qs = urllib.parse.urlencode(params, doseq=True)
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{qs}"


def _build_headers(user_agent_suffix: str, etag: str | None, extra: dict[str, str] | None) -> dict[str, str]:
    ua = USER_AGENT_BASE
    if user_agent_suffix:
        ua = f"{ua} {user_agent_suffix}"
    headers = {"User-Agent": ua}
    if etag:
        headers["If-None-Match"] = etag
    if extra:
        headers.update(extra)
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
    timeout: int,
) -> tuple[int, bytes, dict[str, str]]:
    """Execute HTTP GET. Returns (status, body_bytes, response_headers).

    Raises urllib.error.HTTPError on non-2xx (304 included — caller handles).
    Raises socket.timeout on timeout, urllib.error.URLError on connection failure.
    """
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        resp_headers = dict(resp.headers) if hasattr(resp, "headers") else {}
        status = resp.getcode() if hasattr(resp, "getcode") else 200
        return status, body, resp_headers


def _fetch_raw(
    url: str,
    *,
    params: dict[str, Any] | None,
    cache_key: str | None,
    cache_ttl_hours: int,
    user_agent_suffix: str,
    extra_headers: dict[str, str] | None,
    timeout: int,
) -> dict[str, Any]:
    """Core GET logic with ETag cache + retry. Returns envelope with raw body bytes."""
    final_url = _build_url(url, params)
    cached = _read_cache_entry(cache_key, cache_ttl_hours)
    etag = cached.get("etag") if cached else None

    headers = _build_headers(user_agent_suffix, etag, extra_headers)

    def _try_once() -> dict[str, Any]:
        try:
            status, body, resp_headers = _perform_request(final_url, headers, timeout)
            new_etag = resp_headers.get("ETag") or resp_headers.get("Etag")
            return {"status": status, "body": body, "etag": new_etag, "error": None}
        except urllib.error.HTTPError as err:
            if err.code == 304 and cached is not None:
                return {"status": 304, "body": None, "etag": etag, "error": None, "_use_cached": True}
            if err.code == 404:
                return {"status": 404, "body": None, "etag": None, "error": "not_found"}
            if err.code in (429, 503):
                return {"status": err.code, "body": None, "etag": None, "error": "rate_limited", "_retry_after": _retry_after_seconds(err)}
            return {"status": err.code, "body": None, "etag": None, "error": f"http_{err.code}"}
        except socket.timeout:
            return {"status": 0, "body": None, "etag": None, "error": "timeout"}
        except urllib.error.URLError as err:
            reason = str(getattr(err, "reason", err))
            if "timed out" in reason.lower():
                return {"status": 0, "body": None, "etag": None, "error": "timeout"}
            return {"status": 0, "body": None, "etag": None, "error": f"network_error: {reason}"}
        except Exception as err:  # defensive catch-all
            return {"status": 0, "body": None, "etag": None, "error": f"unexpected: {type(err).__name__}"}

    result = _try_once()
    # One retry on rate_limited — sleep then retry
    if result.get("error") == "rate_limited":
        time.sleep(result.get("_retry_after", 1))
        result = _try_once()

    return result


def fetch_json(
    url: str,
    *,
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
        params=params,
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
    params: dict[str, Any] | None = None,
    cache_key: str | None = None,
    cache_ttl_hours: int = DEFAULT_CACHE_TTL_HOURS,
    user_agent_suffix: str = "",
    extra_headers: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """GET + parse XML. Returns {"items": <ElementTree root>, "error": None|str}. Never raises.

    XML bodies are NOT cached across 304 round-trips (cache stores dicts; XML roots
    are not JSON-serializable). ETag cache still provides bandwidth savings on 304
    by re-fetching on cache miss. Callers that want to cache should wrap the parsed
    root in a source-specific extractor before storing.
    """
    raw = _fetch_raw(
        url,
        params=params,
        cache_key=None,  # skip cache for XML — see docstring
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
