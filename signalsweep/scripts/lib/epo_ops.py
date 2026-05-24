"""EPO Open Patent Services (OPS) — European patents (signalsweep 3.15.0+).

European Patent Office's OPS API surfaces European patent bibliographic
data, full-text, and family information. Free tier: 4GB/month after free
registration at developers.epo.org.

Auth: OAuth 2.0 client-credentials flow. EPO uses HTTP Basic auth on the
token endpoint (base64(consumer_key:consumer_secret)), which is a small
distinction from the form-encoded OAuth shape in `marketplace_oauth.py`.
Given this quirk and EPO's otherwise isolated use, we keep the OAuth
helper inline rather than extending `marketplace_oauth.py` with a flag.

Env:
  `EPO_OPS_CONSUMER_KEY`
  `EPO_OPS_CONSUMER_SECRET`

Envelope-first: missing credentials → `credentials_missing`.

Docs: developers.epo.org/ops-v3-2/apis
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import urllib.parse
from typing import Any

from . import paid_api


TOKEN_URL = "https://ops.epo.org/3.2/auth/accesstoken"
SEARCH_URL = "https://ops.epo.org/3.2/rest-services/published-data/search/biblio"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}

EXPIRY_BUFFER_SECONDS = 300  # 5-minute buffer

# Process-local token cache keyed by sha256(consumer_key).
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_LAST_ERROR: dict[str, str] = {}


def _cache_key(consumer_key: str) -> str:
    return hashlib.sha256(consumer_key.encode("utf-8")).hexdigest()[:32]


def _get_access_token(consumer_key: str, consumer_secret: str, *, force_refresh: bool = False) -> str | None:
    """OAuth 2.0 client-credentials via HTTP Basic auth on token endpoint."""
    if not (consumer_key and consumer_secret):
        _LAST_ERROR["reason"] = "missing_credentials"
        return None

    key = _cache_key(consumer_key)
    if not force_refresh:
        cached = _TOKEN_CACHE.get(key)
        if cached and cached[1] > (time.time() + EXPIRY_BUFFER_SECONDS):
            return cached[0]

    basic = base64.b64encode(f"{consumer_key}:{consumer_secret}".encode("utf-8")).decode("ascii")
    body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")

    raw = paid_api._fetch_raw(
        TOKEN_URL,
        method="POST",
        body=body,
        params=None,
        auth=None,
        cache_key=None,
        cache_ttl_hours=0,
        user_agent_suffix="(epo_ops-auth)",
        extra_headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout=15,
    )
    err = raw.get("error")
    if err:
        _LAST_ERROR["reason"] = err
        return None

    raw_body = raw.get("body") or b""
    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except (UnicodeDecodeError, ValueError) as exc:
        _LAST_ERROR["reason"] = f"parse_error: {exc}"
        return None

    access_token = payload.get("access_token")
    if not access_token or not isinstance(access_token, str):
        _LAST_ERROR["reason"] = "no_access_token_in_response"
        return None

    try:
        expires_in = float(payload.get("expires_in", 1200))  # EPO default ~20min
    except (TypeError, ValueError):
        expires_in = 1200
    _TOKEN_CACHE[key] = (access_token, time.time() + expires_in)
    _LAST_ERROR.pop("reason", None)
    return access_token


def clear_cache() -> None:
    _TOKEN_CACHE.clear()
    _LAST_ERROR.clear()


def get_last_error() -> str | None:
    return _LAST_ERROR.get("reason")


def search_epo_ops(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}

    consumer_key = config.get("EPO_OPS_CONSUMER_KEY") or ""
    consumer_secret = config.get("EPO_OPS_CONSUMER_SECRET") or ""
    if not (consumer_key and consumer_secret):
        return {"items": None, "error": "credentials_missing"}

    token = _get_access_token(consumer_key, consumer_secret)
    if not token:
        reason = get_last_error() or ""
        if "401" in reason or "403" in reason or "invalid" in reason.lower():
            return {"items": None, "error": "credentials_invalid"}
        return {"items": None, "error": f"oauth_error: {reason or 'unknown'}"}

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    # EPO CQL query syntax: ta=<term> (title/abstract).
    # Quote terms with spaces.
    cql_topic = f'"{topic}"' if " " in topic else topic
    params: dict[str, Any] = {"q": f"ta={cql_topic}", "Range": f"1-{limit}"}

    result = paid_api.fetch_json(
        SEARCH_URL,
        params=params,
        cache_key=None,  # seller-specific-ish, skip caching
        user_agent_suffix="(epo_ops-adapter)",
        extra_headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )

    # Retry once on 401 with fresh token
    err = (result.get("error") or "") if isinstance(result.get("error"), str) else ""
    if "401" in err or err == "credentials_invalid":
        token = _get_access_token(consumer_key, consumer_secret, force_refresh=True)
        if not token:
            return {"items": None, "error": "credentials_invalid"}
        result = paid_api.fetch_json(
            SEARCH_URL,
            params=params,
            cache_key=None,
            user_agent_suffix="(epo_ops-adapter)",
            extra_headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
        )
    return result


def parse_epo_ops_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    payload = response["items"]
    if not isinstance(payload, dict):
        return []

    # EPO OPS JSON envelope: ops:world-patent-data → ops:biblio-search → ops:search-result → ops:publication-reference
    # The response is deeply nested; we parse defensively.
    root = payload.get("ops:world-patent-data") or payload
    if not isinstance(root, dict):
        return []
    search_block = root.get("ops:biblio-search") or {}
    if not isinstance(search_block, dict):
        return []
    results_block = search_block.get("ops:search-result") or {}
    if not isinstance(results_block, dict):
        return []
    refs = results_block.get("ops:publication-reference") or []
    # Single result comes back as dict, multiple as list
    if isinstance(refs, dict):
        refs = [refs]
    if not isinstance(refs, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for ref in refs[:limit]:
        if not isinstance(ref, dict):
            continue
        # document-id contains country + doc-number + kind + date
        doc_id_block = ref.get("document-id") or {}
        if isinstance(doc_id_block, list):
            doc_id_block = doc_id_block[0] if doc_id_block else {}
        if not isinstance(doc_id_block, dict):
            continue

        country = (doc_id_block.get("country") or {}).get("$", "") if isinstance(doc_id_block.get("country"), dict) else str(doc_id_block.get("country", ""))
        doc_number = (doc_id_block.get("doc-number") or {}).get("$", "") if isinstance(doc_id_block.get("doc-number"), dict) else str(doc_id_block.get("doc-number", ""))
        kind = (doc_id_block.get("kind") or {}).get("$", "") if isinstance(doc_id_block.get("kind"), dict) else str(doc_id_block.get("kind", ""))
        date_field = (doc_id_block.get("date") or {}).get("$", "") if isinstance(doc_id_block.get("date"), dict) else str(doc_id_block.get("date", ""))

        if not (country and doc_number):
            continue

        publication_id = f"{country}{doc_number}{kind}" if kind else f"{country}{doc_number}"
        # EPO date format YYYYMMDD → ISO
        pub_date = date_field
        if date_field and len(date_field) == 8 and date_field.isdigit():
            pub_date = f"{date_field[:4]}-{date_field[4:6]}-{date_field[6:8]}"

        parsed.append({
            "id": f"epo:{publication_id}",
            "title": f"{publication_id} (European patent reference)",
            "snippet": f"EPO publication {publication_id} — {country} Office, filed {pub_date}",
            "url": f"https://worldwide.espacenet.com/patent/search?q={publication_id}",
            "source_domain": "epo.org",
            "date": pub_date or None,
            "relevance": 0.7,
            "why_relevant": f"EPO patent reference for '{query[:40]}'" if query else publication_id,
            "metadata": {
                "publication_id": publication_id,
                "country": country,
                "doc_number": doc_number,
                "kind_code": kind,
            },
        })
    return parsed
