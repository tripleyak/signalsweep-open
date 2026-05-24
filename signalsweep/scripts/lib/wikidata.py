"""Wikidata entity search via wbsearchentities REST API (signalsweep 3.6.1+).

No auth required. Uses the simple wbsearchentities action (NOT SPARQL) for
v3.6.1 — covers the entity-resolution use case (query string → Q-id).
SPARQL deferred to v3.6.2+ if richer relationship queries become valuable.

Endpoint: https://www.wikidata.org/w/api.php
"""

from __future__ import annotations

from typing import Any

from . import public_api


SEARCH_URL = "https://www.wikidata.org/w/api.php"

DEPTH_LIMITS = {
    "quick": 7,    # wbsearchentities caps `limit` at 50 but defaults to 7
    "default": 25,
    "deep": 50,
}


def search_wikidata(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve query string to Wikidata entities."""
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {
        "action": "wbsearchentities",
        "search": topic,
        "language": "en",
        "format": "json",
        "limit": limit,
        "type": "item",
    }
    return public_api.fetch_json(
        SEARCH_URL,
        params=params,
        cache_key=f"wikidata:{topic}:{depth}",
        user_agent_suffix="(wikidata-adapter)",
    )


def _absolute_url(url: str) -> str:
    """Wikidata returns protocol-relative URLs like //www.wikidata.org/wiki/Q312."""
    if not url:
        return ""
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"https://www.wikidata.org{url}"
    return url


def parse_wikidata_response(
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

    results = payload.get("search") or []
    if not isinstance(results, list):
        return []

    parsed = []
    for r in results:
        if not isinstance(r, dict):
            continue
        qid = (r.get("id") or "").strip()
        label = (r.get("label") or qid).strip()
        description = (r.get("description") or "").strip()
        url = _absolute_url(r.get("concepturi") or r.get("url") or "")

        if not qid:
            continue

        if not url:
            url = f"https://www.wikidata.org/wiki/{qid}"

        parsed.append({
            "id": qid,
            "title": label,
            "snippet": description[:500],
            "url": url,
            "date": to_date or None,
            "source_domain": "wikidata.org",
            "relevance": 0.7,
            "why_relevant": f"Wikidata entity: {label}",
            "metadata": {
                "qid": qid,
                "match_type": (r.get("match") or {}).get("type", ""),
                "match_text": (r.get("match") or {}).get("text", ""),
            },
        })
    return parsed
