"""Helium10 Amazon seller-tool search (signalsweep 3.7+).

Helium10 exposes several product/keyword APIs (Black Box, Xray, Cerebro).
For signalsweep research queries, Black Box — product search by keyword —
maps cleanest to the `search(query) -> items` contract.

Auth: `HELIUM10_API_KEY` as `x-api-key` header. Requires Platinum+ tier.

Endpoint path below is the current (Apr 2026) documented Black Box product
endpoint. If Helium10 migrates routes, adjust `SEARCH_URL` + response field
mapping; module-level contract stays the same.

Cache TTL: 12h — keyword/product data changes faster than BSR.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

SEARCH_URL = "https://api.helium10.com/v1/blackbox/products"

DEPTH_LIMITS = {
    "quick": 10,
    "default": 25,
    "deep": 50,
}


def search_helium10(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search Helium10 Black Box for products matching topic."""
    config = config or {}
    api_key = config.get("HELIUM10_API_KEY") or ""
    if not api_key:
        return {"items": None, "error": "credentials_missing"}

    auth = paid_api.AuthSpec(type="header", name="x-api-key", value=api_key)
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {
        "keyword": topic,
        "limit": limit,
        "marketplace": "US",
    }
    return paid_api.fetch_json(
        SEARCH_URL,
        auth=auth,
        params=params,
        cache_key=f"helium10:{topic}:{depth}",
        cache_ttl_hours=12,
        user_agent_suffix="(helium10-adapter)",
    )


def parse_helium10_response(response: dict[str, Any], query: str = "") -> list[dict[str, Any]]:
    """Parse Helium10 Black Box response into normalized item dicts."""
    if response.get("error") or not response.get("items"):
        return []

    body = response["items"]
    if not isinstance(body, dict):
        return []

    # Helium10 responses vary by endpoint version — handle several common shapes.
    products = body.get("products") or body.get("data") or body.get("results") or []
    if not isinstance(products, list):
        return []

    parsed = []
    for i, p in enumerate(products):
        if not isinstance(p, dict):
            continue
        asin = p.get("asin") or p.get("ASIN") or ""
        title = (p.get("title") or p.get("product_title") or "").strip()
        if not asin or not title:
            continue

        brand = (p.get("brand") or "").strip()
        bsr = p.get("bsr") or p.get("sales_rank")
        price = p.get("price")  # typically dollars float, not cents
        monthly_revenue = p.get("monthly_revenue") or p.get("revenue")
        monthly_sales = p.get("monthly_sales") or p.get("sales")

        snippet_parts = []
        if brand:
            snippet_parts.append(f"Brand: {brand}")
        if bsr:
            snippet_parts.append(f"BSR: #{bsr:,}" if isinstance(bsr, int) else f"BSR: {bsr}")
        if monthly_revenue:
            snippet_parts.append(f"Monthly revenue: ${monthly_revenue:,.0f}" if isinstance(monthly_revenue, (int, float)) else f"Monthly revenue: {monthly_revenue}")
        if monthly_sales:
            snippet_parts.append(f"Monthly sales: {monthly_sales:,}" if isinstance(monthly_sales, (int, float)) else f"Monthly sales: {monthly_sales}")
        snippet = " · ".join(snippet_parts) or f"Helium10 product (ASIN {asin})"

        parsed.append({
            "id": asin,
            "title": title,
            "snippet": snippet,
            "url": f"https://www.amazon.com/dp/{asin}",
            "source_domain": "amazon.com",
            "date": None,
            "relevance": max(0.3, 1.0 - (i * 0.03)),
            "why_relevant": f"Helium10 product match for '{query}'" if query else "Helium10 product match",
            "metadata": {
                "asin": asin,
                "brand": brand,
                "bsr": bsr,
                "price": price,
                "monthly_revenue": monthly_revenue,
                "monthly_sales": monthly_sales,
            },
        })
    return parsed
