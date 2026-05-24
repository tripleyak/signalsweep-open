"""Google Shopping-style product aggregation via Exa (signalsweep 3.7+).

Exa doesn't have a dedicated Google Shopping endpoint, but its neural search
with `includeDomains` filtered to major ecommerce storefronts gives a strong
approximation: shopping-intent results from amazon.com, walmart.com,
target.com, ebay.com, and major DTC brand sites.

Auth: reuses `EXA_API_KEY` (already set in user's env for v3 grounding).

If Exa's product-result richness proves insufficient (no price/merchant
metadata), v3.7.1 can add a SerpAPI fallback gated on `SERPAPI_API_KEY`. The
Exa path ships first because zero additional env setup is needed.

Cache TTL: 6h — product availability + pricing changes faster than most v3.6
sources.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from . import http

EXA_SEARCH_URL = "https://api.exa.ai/search"

# Major shopping domains Exa should prefer for shopping-intent queries.
SHOPPING_DOMAINS = [
    "amazon.com",
    "walmart.com",
    "target.com",
    "ebay.com",
    "bestbuy.com",
    "homedepot.com",
    "lowes.com",
    "costco.com",
    "shopify.com",
    "etsy.com",
    "wayfair.com",
]

DEPTH_CONFIG = {
    "quick": 5,
    "default": 10,
    "deep": 20,
}


def search_google_shopping(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search shopping-domain pages matching topic via Exa."""
    config = config or {}
    api_key = config.get("EXA_API_KEY") or ""
    if not api_key:
        return {"items": None, "error": "credentials_missing"}

    count = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])
    payload = {
        "query": topic,
        "type": "auto",
        "numResults": count,
        "includeDomains": SHOPPING_DOMAINS,
        "contents": {"text": {"maxCharacters": 1500}},
    }
    try:
        data = http.request(
            "POST",
            EXA_SEARCH_URL,
            headers={"x-api-key": api_key},
            json_data=payload,
            timeout=20,
        )
    except Exception as e:
        return {"items": None, "error": f"exa_error: {e}"}

    return {"items": data, "error": None}


def _domain(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc.removeprefix("www.")
    except Exception:
        return ""


def _detect_merchant(url: str) -> str:
    d = _domain(url)
    mapping = {
        "amazon.com": "Amazon",
        "walmart.com": "Walmart",
        "target.com": "Target",
        "ebay.com": "eBay",
        "bestbuy.com": "Best Buy",
        "homedepot.com": "The Home Depot",
        "lowes.com": "Lowe's",
        "costco.com": "Costco",
        "etsy.com": "Etsy",
        "wayfair.com": "Wayfair",
    }
    return mapping.get(d, d or "")


def parse_google_shopping_response(response: dict[str, Any], query: str = "") -> list[dict[str, Any]]:
    """Parse Exa shopping-filtered response into normalized item dicts."""
    if response.get("error") or not response.get("items"):
        return []

    body = response["items"]
    if not isinstance(body, dict):
        return []

    results = body.get("results") or []
    if not isinstance(results, list):
        return []

    parsed = []
    for i, r in enumerate(results):
        if not isinstance(r, dict):
            continue
        url = (r.get("url") or "").strip()
        title = (r.get("title") or "").strip()
        if not url or not title:
            continue

        text = (r.get("text") or "")[:500]
        raw_date = r.get("publishedDate") or ""
        pub_date = raw_date.split("T")[0] if "T" in raw_date else (raw_date[:10] if raw_date else None)
        merchant = _detect_merchant(url)

        snippet_parts = []
        if merchant:
            snippet_parts.append(f"Merchant: {merchant}")
        if text:
            snippet_parts.append(text[:200])
        snippet = " · ".join(snippet_parts) or title

        parsed.append({
            "id": f"GS{i + 1}",
            "title": title,
            "snippet": snippet,
            "url": url,
            "source_domain": _domain(url),
            "date": pub_date,
            "relevance": max(0.3, 1.0 - (i * 0.05)),
            "why_relevant": f"Shopping-domain result for '{query}'" if query else "Shopping-domain result",
            "metadata": {
                "merchant": merchant,
                "exa_score": r.get("score"),
                "author": r.get("author"),
            },
        })
    return parsed
