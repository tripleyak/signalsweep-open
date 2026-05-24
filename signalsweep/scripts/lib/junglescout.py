"""Jungle Scout Product Database search (signalsweep 3.7+).

Jungle Scout's Product Database API returns ASIN-level sales/rank/price for
keyword-driven product queries. Requires Suite tier API access.

Auth: `JUNGLESCOUT_API_KEY` as `x-api-key` header.

Endpoint: `/api/v1/product_database/search` (POST body). If Jungle Scout
switches to GET/query-param, adjust here; module-level contract stays stable.

Cache TTL: 12h.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

SEARCH_URL = "https://developer.junglescout.com/api/v1/product_database/search"

DEPTH_LIMITS = {
    "quick": 10,
    "default": 25,
    "deep": 50,
}


def search_junglescout(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search Jungle Scout Product Database for products matching topic."""
    config = config or {}
    api_key = config.get("JUNGLESCOUT_API_KEY") or ""
    if not api_key:
        return {"items": None, "error": "credentials_missing"}

    auth = paid_api.AuthSpec(type="header", name="x-api-key", value=api_key)
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    payload = {
        "include_keywords": [topic],
        "page_size": limit,
        "marketplace": "us",
    }
    return paid_api.post_json(
        SEARCH_URL,
        payload,
        auth=auth,
        user_agent_suffix="(junglescout-adapter)",
    )


def parse_junglescout_response(response: dict[str, Any], query: str = "") -> list[dict[str, Any]]:
    """Parse Jungle Scout Product Database response."""
    if response.get("error") or not response.get("items"):
        return []

    body = response["items"]
    if not isinstance(body, dict):
        return []

    # JSON:API-style: `data` is a list of records with attributes.
    records = body.get("data") or body.get("products") or []
    if not isinstance(records, list):
        return []

    parsed = []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            continue
        attrs = rec.get("attributes") or rec  # handle both JSON:API and flat shapes
        asin = attrs.get("asin") or rec.get("id") or ""
        title = (attrs.get("title") or attrs.get("name") or "").strip()
        if not asin or not title:
            continue

        brand = (attrs.get("brand") or "").strip()
        category = (attrs.get("category") or attrs.get("parent_category") or "").strip()
        price = attrs.get("price")
        rank = attrs.get("rank") or attrs.get("sales_rank")
        est_sales = attrs.get("estimated_sales") or attrs.get("monthly_sales")

        snippet_parts = []
        if brand:
            snippet_parts.append(f"Brand: {brand}")
        if category:
            snippet_parts.append(f"Category: {category}")
        if rank:
            snippet_parts.append(f"BSR: #{rank:,}" if isinstance(rank, int) else f"BSR: {rank}")
        if est_sales:
            snippet_parts.append(f"Est. sales/mo: {est_sales}")
        snippet = " · ".join(snippet_parts) or f"Jungle Scout product (ASIN {asin})"

        parsed.append({
            "id": asin,
            "title": title,
            "snippet": snippet,
            "url": f"https://www.amazon.com/dp/{asin}",
            "source_domain": "amazon.com",
            "date": None,
            "relevance": max(0.3, 1.0 - (i * 0.03)),
            "why_relevant": f"Jungle Scout product match for '{query}'" if query else "Jungle Scout product match",
            "metadata": {
                "asin": asin,
                "brand": brand,
                "category": category,
                "price": price,
                "rank": rank,
                "estimated_sales": est_sales,
            },
        })
    return parsed
