"""Yotpo UGC Reviews API adapter (signalsweep 3.28.0+).

Structured reviews, photos, Q&A, and sentiment from Yotpo-powered stores.
Richer than scrape-based review sources — includes structured star ratings,
sentiment, verified-buyer flags, and custom form fields.

Endpoint: https://api.yotpo.com/v1/apps/{app_key}/reviews
Auth: YOTPO_APP_KEY + YOTPO_SECRET_KEY
Docs: apidocs.yotpo.com

Gated by SIGNALSWEEP_DISABLE_PAID_APIS (v3.7 paid-APIs tier).
"""

from __future__ import annotations

from typing import Any

from . import paid_api

REVIEWS_URL_TEMPLATE = "https://api.yotpo.com/v1/apps/{app_key}/reviews"

DEPTH_LIMITS = {"quick": 5, "default": 20, "deep": 50}


def search_yotpo_reviews(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}

    app_key = (config.get("YOTPO_APP_KEY") or "").strip()
    if not app_key:
        return {"items": None, "error": "credentials_missing"}

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    params: dict[str, Any] = {
        "count": limit,
        "page": 1,
    }
    if topic:
        params["search"] = topic

    return paid_api.fetch_json(
        REVIEWS_URL_TEMPLATE.format(app_key=app_key),
        params=params,
        cache_key=None,
        user_agent_suffix="(yotpo-reviews-adapter)",
    )


def parse_yotpo_reviews_response(
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

    resp = payload.get("response") or payload
    if isinstance(resp, dict):
        reviews = resp.get("reviews") or []
    else:
        reviews = []

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
        rev_id = str(rev_id)

        title = (rev.get("title") or "").strip()
        content = (rev.get("content") or "").strip()
        score = rev.get("score") or rev.get("rating")
        product_title = ""
        product = rev.get("product") or {}
        if isinstance(product, dict):
            product_title = (product.get("name") or product.get("title") or "").strip()

        sentiment = rev.get("sentiment") or ""
        verified = rev.get("verified_buyer") or False
        created = (rev.get("created_at") or "").strip()

        display_title = title or product_title or f"Yotpo review {rev_id}"

        snippet_parts = []
        if content:
            snippet_parts.append(content[:300])
        if score is not None:
            snippet_parts.append(f"Rating: {score}/5")
        if verified:
            snippet_parts.append("Verified buyer")
        if sentiment:
            snippet_parts.append(f"Sentiment: {sentiment}")
        snippet = " · ".join(snippet_parts) or "Yotpo review"

        date = created[:10] if created and len(created) >= 10 else None

        parsed.append({
            "id": f"yotpo:{rev_id}",
            "title": display_title[:200],
            "snippet": snippet[:500],
            "url": "https://www.yotpo.com/",
            "source_domain": "yotpo.com",
            "date": date,
            "relevance": max(0.3, 0.75 - (i * 0.02)),
            "why_relevant": f"Yotpo review for '{query[:40]}'" if query else display_title[:60],
            "metadata": {
                "review_id": rev_id,
                "star_rating": score,
                "sentiment": str(sentiment),
                "verified_buyer": bool(verified),
                "product_title": product_title,
                "signal_type": "review",
            },
        })
    return parsed
