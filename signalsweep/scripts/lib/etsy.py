"""Etsy Open API v3 — marketplace listing search (signalsweep 3.14.0+).

Etsy's Open API v3 surfaces active marketplace listings with price, shop,
tags, images, and category. Read-only listings search is the primary research
lens; seller-scope endpoints require per-shop OAuth.

Auth: OAuth 2.0. Etsy's public `findAllListingActive` endpoint uses
`x-api-key` header (app API key). User-scoped endpoints additionally require
an OAuth access token from a completed consent flow.

Env:
  `ETSY_API_KEY`                 — app API key (header `x-api-key`, required)
  `ETSY_OAUTH_CLIENT_ID`         — app client ID for OAuth refresh (optional)
  `ETSY_OAUTH_CLIENT_SECRET`     — app client secret (optional)
  `ETSY_OAUTH_REFRESH_TOKEN`     — long-lived refresh token (optional)

Envelope-first: missing `ETSY_API_KEY` → `credentials_missing`. Public
endpoints used here don't need OAuth; OAuth creds are plumbed for future
user-scope expansion.

Depth behaviour:
  `quick`   — keyword search (score-sorted) only
  `default` — keyword search + trending (created-sorted), deduped
  `deep`    — keyword + trending + review mining on top 5 results

Docs: developers.etsy.com/documentation/reference
"""

from __future__ import annotations

from typing import Any

from . import paid_api


SEARCH_URL = "https://openapi.etsy.com/v3/application/listings/active"
REVIEWS_URL_TEMPLATE = "https://openapi.etsy.com/v3/application/listings/{listing_id}/reviews"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}
REVIEW_MINING_TOP_N = 5
REVIEW_SNIPPET_MAX_CHARS = 200


def _fetch_score_listings(
    topic: str, limit: int, api_key: str, depth: str,
) -> dict[str, Any]:
    """Fetch listings sorted by relevance score."""
    return paid_api.fetch_json(
        SEARCH_URL,
        params={"keywords": topic, "limit": limit, "sort_on": "score"},
        cache_key=f"etsy:{topic}:{depth}:score",
        user_agent_suffix="(etsy-adapter)",
        extra_headers={"x-api-key": api_key},
    )


def _fetch_trending_listings(
    topic: str, limit: int, api_key: str, depth: str,
) -> dict[str, Any]:
    """Fetch listings sorted by creation date (newest first) for trending signal."""
    return paid_api.fetch_json(
        SEARCH_URL,
        params={
            "keywords": topic,
            "limit": limit,
            "sort_on": "created",
            "sort_order": "down",
        },
        cache_key=f"etsy:{topic}:{depth}:created",
        user_agent_suffix="(etsy-adapter)",
        extra_headers={"x-api-key": api_key},
    )


def _merge_listing_results(
    score_resp: dict[str, Any],
    trending_resp: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge score-sorted and created-sorted results, deduped by listing_id."""
    score_payload = (score_resp.get("items") or {}) if not score_resp.get("error") else {}
    score_listings = score_payload.get("results") or score_payload.get("listings") or [] \
        if isinstance(score_payload, dict) else []

    if trending_resp is None or trending_resp.get("error"):
        return score_resp

    trending_payload = trending_resp.get("items") or {}
    trending_listings = trending_payload.get("results") or trending_payload.get("listings") or [] \
        if isinstance(trending_payload, dict) else []

    seen_ids: set[Any] = set()
    merged: list[dict[str, Any]] = []
    for listing in score_listings:
        if not isinstance(listing, dict):
            continue
        lid = listing.get("listing_id") or listing.get("id")
        if lid and lid not in seen_ids:
            seen_ids.add(lid)
            merged.append(listing)
    for listing in trending_listings:
        if not isinstance(listing, dict):
            continue
        lid = listing.get("listing_id") or listing.get("id")
        if lid and lid not in seen_ids:
            seen_ids.add(lid)
            merged.append(listing)

    return {"items": {"results": merged}, "error": None}


def _fetch_reviews_for_listing(
    listing_id: int | str, api_key: str,
) -> dict[str, Any] | None:
    """Fetch reviews for a single listing. Returns the raw response or None."""
    url = REVIEWS_URL_TEMPLATE.format(listing_id=listing_id)
    resp = paid_api.fetch_json(
        url,
        params={},
        cache_key=f"etsy:reviews:{listing_id}",
        user_agent_suffix="(etsy-adapter)",
        extra_headers={"x-api-key": api_key},
    )
    if resp.get("error"):
        return None
    return resp


def _enrich_with_reviews(
    merged_resp: dict[str, Any], api_key: str,
) -> dict[str, Any]:
    """For the top N listings in merged results, fetch and attach review data."""
    payload = merged_resp.get("items")
    if not isinstance(payload, dict):
        return merged_resp

    listings = payload.get("results") or payload.get("listings") or []
    if not isinstance(listings, list):
        return merged_resp

    for listing in listings[:REVIEW_MINING_TOP_N]:
        if not isinstance(listing, dict):
            continue
        lid = listing.get("listing_id") or listing.get("id")
        if not lid:
            continue
        review_resp = _fetch_reviews_for_listing(lid, api_key)
        if review_resp is None:
            continue
        review_items = review_resp.get("items")
        if not isinstance(review_items, dict):
            continue
        reviews = review_items.get("results") or []
        if not isinstance(reviews, list) or not reviews:
            continue
        first = reviews[0] if isinstance(reviews[0], dict) else {}
        review_text = (first.get("review") or first.get("text") or "")[:REVIEW_SNIPPET_MAX_CHARS]
        review_rating = first.get("rating")
        listing["_review_text"] = review_text
        listing["_review_rating"] = review_rating

    return merged_resp


def search_etsy(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}

    api_key = config.get("ETSY_API_KEY") or ""
    if not api_key:
        return {"items": None, "error": "credentials_missing"}

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    # 1. Score-sorted keyword search (all depths)
    score_resp = _fetch_score_listings(topic, limit, api_key, depth)

    # 2. Trending (created-sorted) — default + deep only
    trending_resp = None
    if depth in ("default", "deep"):
        trending_resp = _fetch_trending_listings(topic, limit, api_key, depth)

    # 3. Merge & dedupe
    merged = _merge_listing_results(score_resp, trending_resp)

    # 4. Review mining — deep only, top 5 listings
    if depth == "deep":
        merged = _enrich_with_reviews(merged, api_key)

    return merged


def parse_etsy_response(
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

    listings = payload.get("results") or payload.get("listings") or []
    if not isinstance(listings, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for listing in listings[:limit]:
        if not isinstance(listing, dict):
            continue
        listing_id = listing.get("listing_id") or listing.get("id") or ""
        title = (listing.get("title") or "").strip()
        if not listing_id or not title:
            continue

        description = (listing.get("description") or "")[:500]
        shop_id = listing.get("shop_id") or ""
        tags = listing.get("tags") or []
        price_obj = listing.get("price") or {}
        try:
            price_amount = int(price_obj.get("amount", 0)) if isinstance(price_obj, dict) else 0
            price_divisor = int(price_obj.get("divisor", 100)) if isinstance(price_obj, dict) else 100
            price_usd = price_amount / price_divisor if price_divisor else 0
        except (TypeError, ValueError):
            price_usd = 0.0
        currency = price_obj.get("currency_code", "USD") if isinstance(price_obj, dict) else "USD"

        try:
            views = int(listing.get("views", 0) or 0)
        except (TypeError, ValueError):
            views = 0
        try:
            favorites = int(listing.get("num_favorers", 0) or 0)
        except (TypeError, ValueError):
            favorites = 0

        url = listing.get("url") or f"https://www.etsy.com/listing/{listing_id}"

        # Extract creation date from listing timestamp
        creation_ts = listing.get("created_timestamp") or listing.get("creation_tsz")
        listing_creation_date = None
        if creation_ts is not None:
            try:
                import datetime
                listing_creation_date = datetime.datetime.fromtimestamp(
                    int(creation_ts), tz=datetime.timezone.utc
                ).strftime("%Y-%m-%d")
            except (TypeError, ValueError, OSError):
                pass

        metadata: dict[str, Any] = {
            "listing_id": listing_id,
            "shop_id": shop_id,
            "price": price_usd,
            "currency": currency,
            "views": views,
            "favorites": favorites,
            "tags": tags[:15] if isinstance(tags, list) else [],
        }

        if listing_creation_date is not None:
            metadata["listing_creation_date"] = listing_creation_date

        # Attach review data if present (enriched at deep depth)
        review_text = listing.get("_review_text")
        review_rating = listing.get("_review_rating")
        if review_text:
            metadata["review_text"] = review_text
        if review_rating is not None:
            metadata["review_rating"] = review_rating

        parsed.append({
            "id": f"etsy:{listing_id}",
            "title": title[:200],
            "snippet": f"Etsy listing — {currency} {price_usd:.2f}, {views:,} views, {favorites} favorites",
            "url": url,
            "source_domain": "etsy.com",
            "date": to_date or None,
            "relevance": 0.7,
            "why_relevant": f"Etsy marketplace match for '{query[:40]}'" if query else title[:60],
            "engagement_score": float(views + favorites * 10),
            "metadata": metadata,
        })
    return parsed
