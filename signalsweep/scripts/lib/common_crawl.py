"""Common Crawl CDX index search (signalsweep 3.28.0+).

Web-scale long-tail discourse mining via the Common Crawl CDX index API.
Like Wayback Machine CDX but for the broader web crawl (~250B pages).

Endpoint: https://index.commoncrawl.org/CC-MAIN-{latest}-index
No auth required.

Gated by SIGNALSWEEP_DISABLE_PUBLIC_APIS (v3.6 public-data tier).
"""

from __future__ import annotations
from typing import Any
from . import public_api

CDX_URL_TEMPLATE = "https://index.commoncrawl.org/{collection}-index"
DEFAULT_COLLECTION = "CC-MAIN-2026-17"
DEPTH_LIMITS = {"quick": 5, "default": 15, "deep": 30}


def search_common_crawl(topic: str, from_date: str, to_date: str, depth: str = "default", config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    if not public_api.is_public_apis_enabled(config):
        return {"items": None, "error": "public_apis_disabled"}
    collection = config.get("COMMON_CRAWL_COLLECTION") or DEFAULT_COLLECTION
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    url = CDX_URL_TEMPLATE.format(collection=collection)
    return public_api.fetch_json(
        url,
        params={"url": f"*.com/*{topic}*", "output": "json", "limit": limit, "matchType": "domain" if "." not in topic else "exact"},
        cache_key=f"commoncrawl:{collection}:{topic}:{depth}",
        user_agent_suffix="(common-crawl-adapter)",
    )


def parse_common_crawl_response(response: dict[str, Any], query: str = "", from_date: str = "", to_date: str = "", depth: str = "default") -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    payload = response["items"]
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = payload.get("results") or payload.get("items") or []
    else:
        return []
    if not isinstance(records, list):
        return []
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    parsed = []
    for i, rec in enumerate(records[:limit]):
        if not isinstance(rec, dict):
            continue
        url = rec.get("url") or ""
        if not url:
            continue
        timestamp = rec.get("timestamp") or ""
        status = rec.get("status") or rec.get("statuscode") or ""
        mime = rec.get("mime") or rec.get("mime-detected") or ""
        length = rec.get("length") or ""
        digest = rec.get("digest") or ""
        date = ""
        if timestamp and len(str(timestamp)) >= 8:
            ts = str(timestamp)
            date = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
        from urllib.parse import urlparse
        domain = urlparse(url).netloc if url.startswith("http") else url.split("/")[0]
        snippet_parts = []
        if mime:
            snippet_parts.append(f"Type: {mime}")
        if status:
            snippet_parts.append(f"Status: {status}")
        if length:
            snippet_parts.append(f"Size: {length}")
        if date:
            snippet_parts.append(f"Crawled: {date}")
        snippet = " · ".join(snippet_parts) or f"Common Crawl: {url[:80]}"
        parsed.append({
            "id": f"cc:{digest[:16]}" if digest else f"cc:{i}",
            "title": url[:200],
            "snippet": snippet[:500],
            "url": url if url.startswith("http") else f"https://{url}",
            "source_domain": domain or "commoncrawl.org",
            "date": date or None,
            "relevance": max(0.3, 0.6 - (i * 0.02)),
            "why_relevant": f"Common Crawl page for '{query[:40]}'" if query else url[:60],
            "metadata": {"timestamp": str(timestamp), "status": str(status), "mime": mime, "digest": digest, "signal_type": "web_crawl"},
        })
    return parsed
