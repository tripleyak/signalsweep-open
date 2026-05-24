"""Apple App Store Customer Reviews (signalsweep 3.17.0+).

Apple's iTunes Search API + Customer Reviews RSS feed. No auth required.

Two-step:
  1. If topic looks like numeric app_id, skip search.
  2. Otherwise, iTunes Search API → find app_id of top match.
  3. Fetch customer reviews RSS JSON feed → parse reviews.

Endpoints:
  - Search: https://itunes.apple.com/search?term={q}&entity=software&limit=1
  - Reviews: https://itunes.apple.com/{country}/rss/customerreviews/id={app_id}/sortBy=mostRecent/page={n}/json

Tier: v3.6 public-data (gated by `SIGNALSWEEP_DISABLE_PUBLIC_APIS`).

Config:
  `APP_STORE_REVIEWS_COUNTRY` — ISO alpha-2 lowercase (default `us`)
  `APP_STORE_REVIEWS_APP_ID` — optional; if set, skip search step

Docs: developer.apple.com (iTunes Search API is well-documented but legacy).
"""

from __future__ import annotations

from typing import Any

from . import public_api, reviews


SEARCH_URL = "https://itunes.apple.com/search"
REVIEWS_URL_TEMPLATE = "https://itunes.apple.com/{country}/rss/customerreviews/id={app_id}/sortBy=mostRecent/page={page}/json"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def _resolve_app_id(topic: str, country: str) -> tuple[str | None, str]:
    """Return (app_id, app_name) or (None, ''). Skip search if topic is numeric."""
    stripped = topic.strip()
    if stripped.isdigit():
        return stripped, ""  # app name not known without search; keep empty

    result = public_api.fetch_json(
        SEARCH_URL,
        params={"term": stripped, "entity": "software", "country": country, "limit": 1},
        cache_key=f"app_store_search:{stripped}:{country}",
        cache_ttl_hours=24,
        user_agent_suffix="(app_store_reviews-adapter)",
    )
    if result.get("error") or not result.get("items"):
        return None, ""
    payload = result["items"]
    if not isinstance(payload, dict):
        return None, ""
    apps = payload.get("results") or []
    if not isinstance(apps, list) or not apps:
        return None, ""
    top = apps[0]
    if not isinstance(top, dict):
        return None, ""
    app_id = str(top.get("trackId") or "")
    app_name = (top.get("trackName") or "").strip()
    return (app_id or None, app_name)


def search_app_store_reviews(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not public_api.is_public_apis_enabled(config):
        return {"items": None, "error": "public_apis_disabled"}

    country = (config.get("APP_STORE_REVIEWS_COUNTRY") or "us").strip().lower()
    override_id = (config.get("APP_STORE_REVIEWS_APP_ID") or "").strip()

    if override_id:
        app_id, app_name = override_id, ""
    else:
        app_id, app_name = _resolve_app_id(topic, country)
    if not app_id:
        return {"items": {"app_id": None, "app_name": "", "reviews": []}, "error": None}

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    # Each RSS page returns up to 50 reviews. Iterate pages up to 5.
    collected: list[dict[str, Any]] = []
    for page in range(1, 6):
        if len(collected) >= limit:
            break
        url = REVIEWS_URL_TEMPLATE.format(country=country, app_id=app_id, page=page)
        page_result = public_api.fetch_json(
            url,
            cache_key=f"app_store_reviews:{app_id}:{country}:{page}",
            cache_ttl_hours=1,
            user_agent_suffix="(app_store_reviews-adapter)",
        )
        if page_result.get("error") or not page_result.get("items"):
            break
        body = page_result["items"]
        if not isinstance(body, dict):
            break
        feed = body.get("feed") or {}
        if not isinstance(feed, dict):
            break
        entries = feed.get("entry") or []
        # First entry is usually the app metadata; the rest are reviews.
        if isinstance(entries, list):
            # Skip index 0 (app-level) if present and resembles app metadata
            for entry in entries[1:]:
                if isinstance(entry, dict):
                    collected.append(entry)
            if len(entries) <= 1:
                break
        else:
            break
    return {"items": {"app_id": app_id, "app_name": app_name, "reviews": collected[:limit]}, "error": None}


def parse_app_store_reviews_response(
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

    app_id = payload.get("app_id") or ""
    app_name = payload.get("app_name") or query or app_id
    review_list = payload.get("reviews") or []
    if not isinstance(review_list, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for entry in review_list[:limit]:
        if not isinstance(entry, dict):
            continue
        review_id = (entry.get("id") or {}).get("label", "") if isinstance(entry.get("id"), dict) else str(entry.get("id", ""))
        review_text = (entry.get("content") or {}).get("label", "") if isinstance(entry.get("content"), dict) else ""
        rating_raw = (entry.get("im:rating") or {}).get("label", "") if isinstance(entry.get("im:rating"), dict) else ""
        author_obj = entry.get("author") or {}
        author_name = ""
        if isinstance(author_obj, dict):
            name_obj = author_obj.get("name") or {}
            if isinstance(name_obj, dict):
                author_name = name_obj.get("label", "") or ""
        review_date_raw = (entry.get("updated") or {}).get("label", "") if isinstance(entry.get("updated"), dict) else ""
        review_date = review_date_raw[:10] if review_date_raw else None

        if not review_id:
            continue

        item = reviews.build_review_item(
            item_id=f"app_store:{review_id}",
            platform="app_store",
            product_name=app_name or f"App {app_id}",
            url=f"https://apps.apple.com/app/id{app_id}" if app_id else "https://apps.apple.com",
            source_domain="apps.apple.com",
            star_rating=rating_raw,
            review_text=review_text,
            reviewer_id=author_name,
            review_date=review_date,
            author=author_name or None,
            relevance=0.7,
            why_relevant=f"App Store review for {app_name or app_id}",
            extra_metadata={"app_id": app_id},
        )
        parsed.append(item)
    return parsed
