"""DataDive Amazon keyword + competitor intel (signalsweep 3.7+).

DataDive provides keyword research and competitive analysis for Amazon sellers.
API tier-gated; docs are access-controlled. Endpoint below matches DataDive's
public patterns (Apr 2026); if they migrate routes, adjust here.

Auth: `DATADIVE_API_KEY` as `x-api-key` header.

Cache TTL: 12h.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

SEARCH_URL = "https://api.datadive.tools/v1/keywords/search"

DEPTH_LIMITS = {
    "quick": 10,
    "default": 25,
    "deep": 50,
}


def search_datadive(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search DataDive for keyword + product intel matching topic."""
    config = config or {}
    api_key = config.get("DATADIVE_API_KEY") or ""
    if not api_key:
        return {"items": None, "error": "credentials_missing"}

    auth = paid_api.AuthSpec(type="header", name="x-api-key", value=api_key)
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {
        "query": topic,
        "limit": limit,
        "marketplace": "us",
    }
    return paid_api.fetch_json(
        SEARCH_URL,
        auth=auth,
        params=params,
        cache_key=f"datadive:{topic}:{depth}",
        cache_ttl_hours=12,
        user_agent_suffix="(datadive-adapter)",
    )


def parse_datadive_response(response: dict[str, Any], query: str = "") -> list[dict[str, Any]]:
    """Parse DataDive keyword/product response."""
    if response.get("error") or not response.get("items"):
        return []

    body = response["items"]
    if not isinstance(body, dict):
        return []

    records = body.get("keywords") or body.get("data") or body.get("results") or []
    if not isinstance(records, list):
        return []

    parsed = []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            continue
        keyword = (rec.get("keyword") or rec.get("phrase") or "").strip()
        if not keyword:
            continue

        search_volume = rec.get("search_volume") or rec.get("monthly_searches")
        competition = rec.get("competition") or rec.get("difficulty")
        cpc = rec.get("cpc") or rec.get("avg_cpc")
        top_asins = rec.get("top_asins") or rec.get("top_products") or []

        snippet_parts = []
        if search_volume:
            snippet_parts.append(f"Searches/mo: {search_volume:,}" if isinstance(search_volume, int) else f"Searches/mo: {search_volume}")
        if competition is not None:
            snippet_parts.append(f"Competition: {competition}")
        if cpc:
            snippet_parts.append(f"CPC: ${cpc:.2f}" if isinstance(cpc, (int, float)) else f"CPC: {cpc}")
        snippet = " · ".join(snippet_parts) or f"DataDive keyword data for '{keyword}'"

        # Keyword-level results don't have a single ASIN URL; link to Amazon search.
        url = f"https://www.amazon.com/s?k={keyword.replace(' ', '+')}"

        parsed.append({
            "id": f"datadive:{keyword}",
            "title": f"Amazon keyword: {keyword}",
            "snippet": snippet,
            "url": url,
            "source_domain": "amazon.com",
            "date": None,
            "relevance": max(0.3, 1.0 - (i * 0.03)),
            "why_relevant": f"DataDive keyword intel for '{query}'" if query else "DataDive keyword intel",
            "metadata": {
                "keyword": keyword,
                "search_volume": search_volume,
                "competition": competition,
                "cpc": cpc,
                "top_asins": top_asins[:10] if isinstance(top_asins, list) else [],
            },
        })
    return parsed
