"""Keepa Amazon product search (signalsweep 3.7+).

Keepa is a paid product intelligence API for Amazon: price history, BSR (Best
Sellers Rank) trajectory, seller counts, category trees. For signalsweep, we
use it primarily as a research lens: given a query, surface the top-N matching
ASINs with current BSR/price snapshots as research items.

Auth: `KEEPA_API_KEY` as query-param `key`.

Token-cost awareness: Keepa uses a token-bucket (60 tokens/min by default).
Each `/search` call costs ~5 tokens depending on result count. To keep costs
bounded, we cap max_results by depth and read `KEEPA_MAX_CALLS` (default 1)
from config for burst-limit control.

Region: `KEEPA_DOMAIN_ID` selects the Amazon locale (1=US, 2=UK, 3=DE, etc.).
Defaults to 1.

Cache TTL: 24h — BSR history rarely needs minute-level freshness for research.

Rate limit: Keepa returns `Retry-After` on exhaustion; handled by `paid_api`.
"""

from __future__ import annotations

from typing import Any

from . import amazon_marketplaces, paid_api

SEARCH_URL = "https://api.keepa.com/search"
DEFAULT_DOMAIN_ID = "1"  # 1 = US Amazon

DEPTH_LIMITS = {
    "quick": 5,
    "default": 10,
    "deep": 20,
}


def search_keepa(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search Keepa's Amazon product catalog for ASINs matching topic.

    Returns `paid_api` envelope: `{"items": <parsed-json>, "error": None|str}`.
    """
    config = config or {}
    api_key = config.get("KEEPA_API_KEY") or ""
    if not api_key:
        return {"items": None, "error": "credentials_missing"}

    max_results = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    domain_id = str(config.get("KEEPA_DOMAIN_ID") or DEFAULT_DOMAIN_ID)

    auth = paid_api.AuthSpec(type="query_param", name="key", value=api_key)
    params = {
        "domain": domain_id,
        "type": "product",
        "term": topic,
        "page": 0,
        "perPage": max_results,
    }
    return paid_api.fetch_json(
        SEARCH_URL,
        auth=auth,
        params=params,
        cache_key=f"keepa:{topic}:{domain_id}:{depth}",
        cache_ttl_hours=24,
        user_agent_suffix="(keepa-adapter)",
    )


def _amazon_url(asin: str, domain_id: str = DEFAULT_DOMAIN_ID) -> str:
    """Build canonical Amazon product URL from ASIN. Domain-aware.

    Looks up the TLD via amazon_marketplaces (single source of truth for all
    Amazon marketplace metadata). Falls back to .com for unknown Keepa domain
    IDs — preserves v3.7.0 behavior.
    """
    region_code = amazon_marketplaces.region_for_keepa_domain(domain_id)
    marketplace = amazon_marketplaces.get_marketplace(region_code or "US")
    tld = marketplace["tld"] if marketplace else "com"
    return f"https://www.amazon.{tld}/dp/{asin}"


def _current_bsr(product: dict[str, Any]) -> int | None:
    """Extract current BSR from Keepa product. Keepa stores csv arrays; current value is last element of salesRanks[0]."""
    sales_ranks = product.get("salesRanks") or {}
    if isinstance(sales_ranks, dict):
        for rank_list in sales_ranks.values():
            if isinstance(rank_list, list) and rank_list:
                # Keepa CSV: [timestamp, value, timestamp, value, ...]. Last value = most recent.
                last_value = rank_list[-1]
                if isinstance(last_value, int) and last_value > 0:
                    return last_value
    return None


def _current_price_cents(product: dict[str, Any]) -> int | None:
    """Extract current Amazon list price (cents) from Keepa product csv[0]."""
    csv_data = product.get("csv") or []
    if not isinstance(csv_data, list) or not csv_data:
        return None
    amazon_csv = csv_data[0] if len(csv_data) > 0 else None
    if not isinstance(amazon_csv, list) or not amazon_csv:
        return None
    last_value = amazon_csv[-1]
    if isinstance(last_value, int) and last_value > 0:
        return last_value
    return None


def parse_keepa_response(response: dict[str, Any], query: str = "") -> list[dict[str, Any]]:
    """Parse Keepa /search response into normalized item dicts.

    Keepa /search returns `{"products": [...], "tokensLeft": N}`. Each product
    has ASIN, title, brand, categoryTree, salesRanks, csv arrays for price
    history.
    """
    if response.get("error") or not response.get("items"):
        return []

    body = response["items"]
    if not isinstance(body, dict):
        return []

    products = body.get("products") or []
    if not isinstance(products, list):
        return []

    parsed = []
    for i, product in enumerate(products):
        asin = product.get("asin") or ""
        title = (product.get("title") or "").strip()
        brand = (product.get("brand") or "").strip()
        if not asin or not title:
            continue

        domain_id = str(product.get("domainId") or DEFAULT_DOMAIN_ID)
        url = _amazon_url(asin, domain_id)

        bsr = _current_bsr(product)
        price_cents = _current_price_cents(product)

        category_tree = product.get("categoryTree") or []
        if isinstance(category_tree, list) and category_tree:
            primary_category = str(category_tree[0].get("name") or "")
        else:
            primary_category = ""

        snippet_parts = []
        if brand:
            snippet_parts.append(f"Brand: {brand}")
        if bsr:
            snippet_parts.append(f"BSR: #{bsr:,}")
        if price_cents:
            snippet_parts.append(f"Price: ${price_cents / 100:.2f}")
        if primary_category:
            snippet_parts.append(f"Category: {primary_category}")
        snippet = " · ".join(snippet_parts) or f"Amazon product (ASIN {asin})"

        parsed.append({
            "id": asin,
            "title": title,
            "snippet": snippet,
            "url": url,
            "source_domain": "amazon.com",
            "date": None,  # Keepa products are catalog entries, not dated posts
            "relevance": max(0.3, 1.0 - (i * 0.05)),
            "why_relevant": f"Amazon product match for '{query}'" if query else "Amazon product match",
            "metadata": {
                "asin": asin,
                "brand": brand,
                "current_bsr": bsr,
                "current_price_cents": price_cents,
                "primary_category": primary_category,
                "domain_id": domain_id,
            },
        })
    return parsed
