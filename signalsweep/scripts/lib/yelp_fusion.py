"""Yelp Fusion API — local business reviews (signalsweep 3.17.0+).

Yelp Fusion v3 API with free-tier key (500 calls/day). Two-step: find
business by name+location, then fetch reviews.

Auth: `YELP_API_KEY` (Bearer). Envelope-first.

Config:
  `YELP_FUSION_LOCATION` — default `"New York, NY"` (used if topic isn't an ID)

Endpoints:
  - Search: https://api.yelp.com/v3/businesses/search
  - Reviews: https://api.yelp.com/v3/businesses/{id}/reviews

Free-tier cap: max 3 reviews per business returned by Fusion API.

Docs: yelp.com/developers/documentation/v3
"""

from __future__ import annotations

from typing import Any

from . import paid_api, reviews


SEARCH_URL = "https://api.yelp.com/v3/businesses/search"
REVIEWS_URL_TEMPLATE = "https://api.yelp.com/v3/businesses/{business_id}/reviews"

DEPTH_LIMITS = {"quick": 3, "default": 3, "deep": 3}  # Yelp caps at 3


def search_yelp_fusion(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}

    api_key = config.get("YELP_API_KEY") or ""
    if not api_key:
        return {"items": None, "error": "credentials_missing"}

    location = config.get("YELP_FUSION_LOCATION") or "New York, NY"
    headers = {"Authorization": f"Bearer {api_key}"}

    # If topic looks like a Yelp business id (contains hyphens, alphanumeric, no spaces),
    # try it as a business_id first. Otherwise search.
    business_id = topic.strip() if ("-" in topic and " " not in topic) else ""

    business_name = ""
    if not business_id:
        search_result = paid_api.fetch_json(
            SEARCH_URL,
            params={"term": topic, "location": location, "limit": 1},
            cache_key=None,
            user_agent_suffix="(yelp_fusion-adapter)",
            extra_headers=headers,
        )
        err = search_result.get("error") or ""
        if isinstance(err, str) and ("401" in err or "403" in err):
            return {"items": None, "error": "credentials_invalid"}
        if err:
            return search_result
        body = search_result.get("items")
        if not isinstance(body, dict):
            return {"items": {"business_id": None, "reviews": []}, "error": None}
        businesses = body.get("businesses") or []
        if not isinstance(businesses, list) or not businesses:
            return {"items": {"business_id": None, "reviews": []}, "error": None}
        top = businesses[0]
        if isinstance(top, dict):
            business_id = top.get("id") or ""
            business_name = top.get("name") or ""

    if not business_id:
        return {"items": {"business_id": None, "reviews": []}, "error": None}

    reviews_result = paid_api.fetch_json(
        REVIEWS_URL_TEMPLATE.format(business_id=business_id),
        cache_key=None,
        user_agent_suffix="(yelp_fusion-adapter)",
        extra_headers=headers,
    )
    err = reviews_result.get("error") or ""
    if isinstance(err, str) and ("401" in err or "403" in err):
        return {"items": None, "error": "credentials_invalid"}
    if err:
        return reviews_result

    body = reviews_result.get("items")
    if not isinstance(body, dict):
        return {"items": {"business_id": business_id, "business_name": business_name, "reviews": []}, "error": None}
    review_list = body.get("reviews") or []
    return {
        "items": {
            "business_id": business_id,
            "business_name": business_name,
            "reviews": review_list if isinstance(review_list, list) else [],
        },
        "error": None,
    }


def parse_yelp_fusion_response(
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

    business_id = payload.get("business_id") or ""
    business_name = payload.get("business_name") or query or business_id
    review_list = payload.get("reviews") or []
    if not isinstance(review_list, list) or not business_id:
        return []

    parsed = []
    for entry in review_list:
        if not isinstance(entry, dict):
            continue
        review_id = entry.get("id") or ""
        review_text = entry.get("text") or ""
        rating = entry.get("rating") or 0
        user_obj = entry.get("user") or {}
        author_name = user_obj.get("name") if isinstance(user_obj, dict) else ""
        review_date = (entry.get("time_created") or "")[:10]

        if not review_id:
            continue

        item = reviews.build_review_item(
            item_id=f"yelp:{review_id}",
            platform="yelp",
            product_name=business_name,
            url=entry.get("url") or f"https://www.yelp.com/biz/{business_id}",
            source_domain="yelp.com",
            star_rating=rating,
            review_text=review_text,
            reviewer_id=(user_obj.get("id") if isinstance(user_obj, dict) else ""),
            review_date=review_date or None,
            author=author_name or None,
            relevance=0.65,
            why_relevant=f"Yelp review for {business_name[:60]}",
            extra_metadata={"business_id": business_id},
        )
        parsed.append(item)
    return parsed
