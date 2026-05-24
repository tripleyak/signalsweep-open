"""PowerReviews API adapter (signalsweep 3.28.0+).

Reviews, Q&A, and product feedback from PowerReviews-powered retailers.

Endpoint: https://readservices-b2c.powerreviews.com/m/{merchant_id}/l/{locale}/product/{page_id}/reviews
Auth: POWERREVIEWS_API_KEY + POWERREVIEWS_MERCHANT_ID.

Gated by SIGNALSWEEP_DISABLE_PAID_APIS (v3.7 paid-APIs tier).
"""

from __future__ import annotations
from typing import Any
from . import paid_api

REVIEWS_URL_TEMPLATE = "https://readservices-b2c.powerreviews.com/m/{merchant_id}/l/en_US/product/{product_id}/reviews"
DEPTH_LIMITS = {"quick": 5, "default": 15, "deep": 30}


def search_powerreviews(topic: str, from_date: str, to_date: str, depth: str = "default", config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = (config.get("POWERREVIEWS_API_KEY") or "").strip()
    merchant_id = (config.get("POWERREVIEWS_MERCHANT_ID") or "").strip()
    if not (api_key and merchant_id):
        return {"items": None, "error": "credentials_missing"}
    product_id = topic.replace(" ", "-")[:50]
    url = REVIEWS_URL_TEMPLATE.format(merchant_id=merchant_id, product_id=product_id)
    return paid_api.fetch_json(
        url,
        params={"apikey": api_key, "_noconfig": "true", "paging.size": DEPTH_LIMITS.get(depth, 15)},
        cache_key=f"powerreviews:{merchant_id}:{product_id}:{depth}",
        user_agent_suffix="(powerreviews-adapter)",
    )


def parse_powerreviews_response(response: dict[str, Any], query: str = "", from_date: str = "", to_date: str = "", depth: str = "default") -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    payload = response["items"]
    if not isinstance(payload, dict):
        return []
    results = payload.get("results") or []
    if isinstance(results, list) and results and isinstance(results[0], dict):
        reviews = results[0].get("reviews") or []
    else:
        reviews = []
    if not isinstance(reviews, list):
        return []
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    parsed = []
    for i, rev in enumerate(reviews[:limit]):
        if not isinstance(rev, dict):
            continue
        rev_id = rev.get("review_id") or rev.get("id") or ""
        if not rev_id:
            continue
        headline = (rev.get("headline") or "").strip()
        comments = (rev.get("comments") or "").strip()
        rating = rev.get("rating") or rev.get("metrics", {}).get("rating")
        bottom_line = (rev.get("bottom_line") or "").strip()
        snippet_parts = []
        if headline:
            snippet_parts.append(headline[:200])
        if comments:
            snippet_parts.append(comments[:200])
        if rating:
            snippet_parts.append(f"Rating: {rating}/5")
        if bottom_line:
            snippet_parts.append(f"Recommend: {bottom_line}")
        snippet = " · ".join(snippet_parts) or "PowerReviews review"
        date = (rev.get("details", {}).get("created_date") or "")[:10] or None
        parsed.append({
            "id": f"powerreviews:{rev_id}",
            "title": (headline or f"Review {rev_id}")[:200],
            "snippet": snippet[:500],
            "url": "https://www.powerreviews.com/",
            "source_domain": "powerreviews.com",
            "date": date,
            "relevance": max(0.3, 0.7 - (i * 0.02)),
            "why_relevant": f"PowerReviews for '{query[:40]}'" if query else (headline or "Review")[:60],
            "metadata": {"review_id": str(rev_id), "star_rating": rating, "bottom_line": bottom_line, "signal_type": "review"},
        })
    return parsed
