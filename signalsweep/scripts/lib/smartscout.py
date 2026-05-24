"""SmartScout Amazon seller / market-share research (signalsweep 3.7+).

SmartScout focuses on seller-level intel: brand-owner lookups, market share,
category tree coverage. API tier-gated.

Auth: `SMARTSCOUT_API_KEY` as `x-api-key` header.

Cache TTL: 12h.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

SEARCH_URL = "https://api.smartscout.com/v1/brands/search"

DEPTH_LIMITS = {
    "quick": 10,
    "default": 25,
    "deep": 50,
}


def search_smartscout(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search SmartScout for brands / sellers matching topic."""
    config = config or {}
    api_key = config.get("SMARTSCOUT_API_KEY") or ""
    if not api_key:
        return {"items": None, "error": "credentials_missing"}

    auth = paid_api.AuthSpec(type="header", name="x-api-key", value=api_key)
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {
        "q": topic,
        "limit": limit,
        "marketplace": "US",
    }
    return paid_api.fetch_json(
        SEARCH_URL,
        auth=auth,
        params=params,
        cache_key=f"smartscout:{topic}:{depth}",
        cache_ttl_hours=12,
        user_agent_suffix="(smartscout-adapter)",
    )


def parse_smartscout_response(response: dict[str, Any], query: str = "") -> list[dict[str, Any]]:
    """Parse SmartScout brands/sellers response."""
    if response.get("error") or not response.get("items"):
        return []

    body = response["items"]
    if not isinstance(body, dict):
        return []

    records = body.get("brands") or body.get("data") or body.get("results") or []
    if not isinstance(records, list):
        return []

    parsed = []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            continue
        brand = (rec.get("brand") or rec.get("name") or "").strip()
        if not brand:
            continue

        monthly_revenue = rec.get("monthly_revenue") or rec.get("revenue")
        market_share = rec.get("market_share")
        num_asins = rec.get("num_asins") or rec.get("asin_count")
        primary_category = (rec.get("primary_category") or rec.get("category") or "").strip()

        snippet_parts = []
        if primary_category:
            snippet_parts.append(f"Category: {primary_category}")
        if monthly_revenue:
            snippet_parts.append(f"Monthly revenue: ${monthly_revenue:,.0f}" if isinstance(monthly_revenue, (int, float)) else f"Monthly revenue: {monthly_revenue}")
        if market_share is not None:
            snippet_parts.append(f"Market share: {market_share:.1%}" if isinstance(market_share, float) and market_share <= 1 else f"Market share: {market_share}")
        if num_asins:
            snippet_parts.append(f"ASINs: {num_asins:,}" if isinstance(num_asins, int) else f"ASINs: {num_asins}")
        snippet = " · ".join(snippet_parts) or f"SmartScout brand: {brand}"

        # Brand-level results link to Amazon brand search.
        url = f"https://www.amazon.com/s?k={brand.replace(' ', '+')}"

        parsed.append({
            "id": f"smartscout:{brand}",
            "title": f"Amazon brand: {brand}",
            "snippet": snippet,
            "url": url,
            "source_domain": "amazon.com",
            "date": None,
            "relevance": max(0.3, 1.0 - (i * 0.03)),
            "why_relevant": f"SmartScout brand intel for '{query}'" if query else "SmartScout brand intel",
            "metadata": {
                "brand": brand,
                "monthly_revenue": monthly_revenue,
                "market_share": market_share,
                "num_asins": num_asins,
                "primary_category": primary_category,
            },
        })
    return parsed
