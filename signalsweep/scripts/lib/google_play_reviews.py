"""Google Play Store review scrape (signalsweep 3.17.0+).

Fetches `play.google.com/store/apps/details?id={package}` HTML and
parses embedded JSON state (Google Play embeds an `AF_initDataCallback`
block with review data).

Tier: v3.7 `SIGNALSWEEP_DISABLE_PAID_APIS`. No credentials. 500ms polite-sleep.

Topic: package name (e.g., `com.example.app`) OR app name for search.

**Risk:** Google may block research scraping aggressively. Adapter surfaces
`rate_limited` envelope on 429 and graceful-degrades on schema drift.

Docs: play.google.com (DevTools; `AF_initDataCallback` is the stable parse target).
"""

from __future__ import annotations

import re
import sys
import time
from typing import Any

from . import paid_api, reviews


BASE_URL = "https://play.google.com/store/apps/details"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}

POLITE_SLEEP_MS = 500

# Package-name regex: 2+ segments separated by dots, alphanumeric+underscore
_PACKAGE_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$")


def _looks_like_package(topic: str) -> bool:
    return bool(_PACKAGE_PATTERN.match(topic.strip()))


def search_google_play_reviews(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}

    topic_stripped = topic.strip()
    if not topic_stripped:
        return {"items": None, "error": "invalid_topic"}

    # Without a search API, require package-name topic. For non-package topics,
    # document in matrix doc and return empty gracefully.
    if not _looks_like_package(topic_stripped):
        sys.stderr.write(
            f"[google_play_reviews] topic '{topic_stripped}' is not a package name; "
            f"Google Play Store lacks a stable search API — pass a package name "
            f"like com.example.app instead\n"
        )
        return {"items": {"package_name": topic_stripped, "html": "", "note": "non-package-topic"}, "error": None}

    package_name = topic_stripped
    params = {"id": package_name, "hl": "en", "gl": "us"}

    raw = paid_api._fetch_raw(
        BASE_URL, method="GET", body=None, params=params, auth=None,
        cache_key=None, cache_ttl_hours=0,
        user_agent_suffix="(google_play_reviews-adapter)",
        extra_headers={"Accept": "text/html,application/xhtml+xml"},
        timeout=15,
    )
    time.sleep(POLITE_SLEEP_MS / 1000.0)

    if raw.get("error"):
        return {"items": None, "error": raw["error"]}

    body = raw.get("body") or b""
    try:
        html = body.decode("utf-8", errors="replace")
    except Exception:
        return {"items": None, "error": "parse_error"}

    return {"items": {"package_name": package_name, "html": html}, "error": None}


def parse_google_play_reviews_response(
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

    package_name = payload.get("package_name") or ""
    html = payload.get("html") or ""
    if not package_name or not html:
        return []

    # Google Play embeds review data in AF_initDataCallback blocks.
    # The app page includes aggregate rating + review count in schema.org JSON-LD
    # (easier to parse) plus sample reviews in the embedded state.
    # We prioritize aggregate rating + a sample of reviews.
    import json as _json

    # Try JSON-LD first — most stable
    json_ld_blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL,
    )
    aggregate_rating = 0.0
    aggregate_count = 0
    app_name = package_name

    for block in json_ld_blocks:
        try:
            data = _json.loads(block.strip())
        except (ValueError, _json.JSONDecodeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for c in candidates:
            if not isinstance(c, dict):
                continue
            if c.get("@type") in ("MobileApplication", "SoftwareApplication"):
                name = c.get("name")
                if name:
                    app_name = str(name)
                rating_obj = c.get("aggregateRating") or {}
                if isinstance(rating_obj, dict):
                    try:
                        aggregate_rating = float(rating_obj.get("ratingValue", 0) or 0)
                    except (TypeError, ValueError):
                        aggregate_rating = 0.0
                    try:
                        aggregate_count = int(rating_obj.get("reviewCount", 0) or 0)
                    except (TypeError, ValueError):
                        aggregate_count = 0

    if aggregate_count == 0:
        sys.stderr.write(
            f"[google_play_reviews] no aggregateRating found for {package_name}; "
            f"Google Play may have changed layout or app not found\n"
        )
        return []

    # Without a reliable parse path for individual reviews in the static HTML
    # (Google loads them dynamically), we emit a single aggregate summary item.
    # Users who need individual reviews should use app_store_reviews (Apple has
    # stable RSS) or a dedicated google-play-scraper library as a future
    # signalsweep dep.
    item = reviews.build_review_item(
        item_id=f"google_play:{package_name}:summary",
        platform="google_play",
        product_name=app_name,
        url=f"https://play.google.com/store/apps/details?id={package_name}",
        source_domain="play.google.com",
        star_rating=aggregate_rating,
        review_count=aggregate_count,
        relevance=0.7,
        why_relevant=f"Google Play aggregate for {app_name}",
        extra_metadata={"package_name": package_name, "summary_only": True},
    )
    return [item]
