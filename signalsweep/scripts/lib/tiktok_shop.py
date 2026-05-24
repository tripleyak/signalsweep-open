"""TikTok Shop product search via ScrapeCreators (signalsweep 3.7+).

Given a product keyword, ScrapeCreators returns TikTok Shop listings with
price, seller, and shoppable-video links.

Auth: reuses `SCRAPECREATORS_API_KEY`.

Mirrors `scripts/lib/linkedin.py` structure.
"""

from __future__ import annotations

import math
import sys
from typing import Any, Dict, List

from . import http

SCRAPECREATORS_URL = "https://api.scrapecreators.com/v1/tiktok/shop/search"

DEPTH_CONFIG = {
    "quick": 10,
    "default": 25,
    "deep": 50,
}


def _log(msg: str) -> None:
    if sys.stderr.isatty():
        sys.stderr.write(f"[TTShop] {msg}\n")
        sys.stderr.flush()


def search_tiktok_shop(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    api_key: str = "",
) -> Dict[str, Any]:
    """Search TikTok Shop listings matching topic."""
    if not api_key:
        return {"listings": [], "error": "SCRAPECREATORS_API_KEY required for TikTok Shop"}

    count = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])
    headers = http.scrapecreators_headers(api_key)
    payload = {
        "query": topic,
        "limit": count,
    }

    try:
        response = http.post(SCRAPECREATORS_URL, payload, headers=headers, timeout=30)
    except Exception as e:
        _log(f"ScrapeCreators TikTok Shop failed: {e}")
        msg = str(e)
        if any(code in msg for code in ("402", "403", "429", "500", "502", "503")):
            msg = "ScrapeCreators unavailable — visit scrapecreators.com to check status"
        return {"listings": [], "error": msg}

    listings = response.get("data", response.get("listings", response.get("products", response.get("results", []))))
    if isinstance(listings, dict):
        listings = listings.get("listings", listings.get("products", []))
    if not isinstance(listings, list):
        listings = []

    _log(f"Found {len(listings)} listings")
    return {"listings": listings}


def parse_tiktok_shop_response(
    response: Dict[str, Any],
    query: str = "",
) -> List[Dict[str, Any]]:
    """Parse TikTok Shop response into normalized item dicts."""
    listings = response.get("listings", [])
    parsed = []

    for i, listing in enumerate(listings):
        if not isinstance(listing, dict):
            continue
        name = (listing.get("name") or listing.get("title") or listing.get("product_name") or "").strip()
        if not name:
            continue

        url = listing.get("url") or listing.get("product_url") or ""
        price = listing.get("price") or listing.get("current_price")
        currency = listing.get("currency") or "USD"
        seller = (listing.get("seller") or listing.get("shop") or "").strip()
        if isinstance(seller, dict):
            seller = (seller.get("name") or "").strip()
        sold_count = listing.get("sold_count") or listing.get("sales")
        rating = listing.get("rating") or listing.get("stars")

        snippet_parts = []
        if seller:
            snippet_parts.append(f"Seller: {seller}")
        if price is not None:
            snippet_parts.append(f"{currency} {price}")
        if sold_count:
            snippet_parts.append(f"Sold: {sold_count:,}" if isinstance(sold_count, int) else f"Sold: {sold_count}")
        if rating:
            snippet_parts.append(f"{rating}★")
        snippet = " · ".join(snippet_parts) or name

        date_str = listing.get("date") or listing.get("created_at") or ""
        if date_str and len(date_str) >= 10:
            date_str = date_str[:10]
        else:
            date_str = None

        rank_score = max(0.3, 1.0 - (i * 0.04))
        sales_boost = min(0.1, math.log1p(sold_count or 0) / 20) if isinstance(sold_count, (int, float)) else 0
        relevance = min(1.0, rank_score + sales_boost)

        parsed.append({
            "id": listing.get("id") or listing.get("product_id") or f"TTS{i + 1}",
            "title": name,
            "snippet": snippet,
            "url": url,
            "source_domain": "tiktok.com",
            "date": date_str,
            "relevance": round(relevance, 2),
            "why_relevant": f"TikTok Shop listing for '{query}'" if query else "TikTok Shop listing",
            "metadata": {
                "seller": seller,
                "price": price,
                "currency": currency,
                "sold_count": sold_count,
                "rating": rating,
            },
        })

    return parsed
