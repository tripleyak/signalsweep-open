"""Stamped.io Reviews API adapter (signalsweep 3.28.0+).

Reviews platform API. Complements Yotpo and PowerReviews.

Endpoint: https://stamped.io/api/v2/{store_hash}/dashboard/reviews
Auth: STAMPED_API_KEY + STAMPED_STORE_HASH.

Gated by SIGNALSWEEP_DISABLE_PAID_APIS (v3.7 paid-APIs tier).
"""

from __future__ import annotations
from typing import Any
from . import paid_api

REVIEWS_URL_TEMPLATE = "https://stamped.io/api/v2/{store_hash}/dashboard/reviews"
DEPTH_LIMITS = {"quick": 5, "default": 15, "deep": 30}


def search_stamped_reviews(topic: str, from_date: str, to_date: str, depth: str = "default", config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = (config.get("STAMPED_API_KEY") or "").strip()
    store_hash = (config.get("STAMPED_STORE_HASH") or "").strip()
    if not (api_key and store_hash):
        return {"items": None, "error": "credentials_missing"}
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    url = REVIEWS_URL_TEMPLATE.format(store_hash=store_hash)
    return paid_api.fetch_json(
        url,
        auth=paid_api.AuthSpec(type="bearer", value=api_key),
        params={"search": topic, "limit": limit},
        cache_key=None,
        user_agent_suffix="(stamped-reviews-adapter)",
    )


def parse_stamped_reviews_response(response: dict[str, Any], query: str = "", from_date: str = "", to_date: str = "", depth: str = "default") -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    payload = response["items"]
    if isinstance(payload, dict):
        reviews = payload.get("data") or payload.get("results") or payload.get("reviews") or []
    elif isinstance(payload, list):
        reviews = payload
    else:
        return []
    if not isinstance(reviews, list):
        return []
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    parsed = []
    for i, rev in enumerate(reviews[:limit]):
        if not isinstance(rev, dict):
            continue
        rev_id = rev.get("id") or ""
        if not rev_id:
            continue
        title = (rev.get("reviewTitle") or rev.get("title") or "").strip()
        body = (rev.get("reviewMessage") or rev.get("body") or "").strip()
        rating = rev.get("reviewRating") or rev.get("rating")
        product = (rev.get("productTitle") or rev.get("productName") or "").strip()
        author = (rev.get("author") or "").strip()
        created = (rev.get("dateCreated") or rev.get("created_at") or "").strip()
        display = title or product or f"Stamped review {rev_id}"
        snippet_parts = []
        if body:
            snippet_parts.append(body[:300])
        if rating:
            snippet_parts.append(f"Rating: {rating}/5")
        if product:
            snippet_parts.append(f"Product: {product[:50]}")
        snippet = " · ".join(snippet_parts) or "Stamped review"
        date = created[:10] if created and len(created) >= 10 else None
        parsed.append({
            "id": f"stamped:{rev_id}",
            "title": display[:200],
            "snippet": snippet[:500],
            "url": "https://stamped.io/",
            "source_domain": "stamped.io",
            "date": date,
            "relevance": max(0.3, 0.7 - (i * 0.02)),
            "why_relevant": f"Stamped review for '{query[:40]}'" if query else display[:60],
            "metadata": {"review_id": str(rev_id), "star_rating": rating, "product_title": product, "signal_type": "review"},
        })
    return parsed
