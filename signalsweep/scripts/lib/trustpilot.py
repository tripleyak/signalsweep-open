"""Trustpilot public review scrape adapter (signalsweep 3.17.0+).

Fetches `trustpilot.com/review/{domain}` HTML and parses embedded JSON-LD
review data (more stable than DOM-scraping review cards).

Tier: v3.7 `SIGNALSWEEP_DISABLE_PAID_APIS` (scrape-friendly research tool).
No credentials required. 500ms polite-sleep per call.

Topic: bare domain (e.g., `example.com`) or full Trustpilot URL (e.g.,
`trustpilot.com/review/example.com`).

Docs: trustpilot.com (DevTools inspection; JSON-LD block is the stable parse target).
"""

from __future__ import annotations

import json
import re
import sys
import time
from typing import Any

from . import paid_api, reviews


BASE_URL = "https://www.trustpilot.com/review"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}

POLITE_SLEEP_MS = 500


def _normalize_domain(topic: str) -> str:
    """Accept bare domain, Trustpilot URL, or full URL; return bare domain."""
    t = topic.strip().lower()
    # Strip known prefixes
    for prefix in ("https://", "http://", "www."):
        if t.startswith(prefix):
            t = t[len(prefix):]
    # Strip trustpilot.com/review/ prefix if present
    if t.startswith("trustpilot.com/review/"):
        t = t[len("trustpilot.com/review/"):]
    # Take first path segment
    return t.split("/", 1)[0]


def search_trustpilot(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}

    domain = _normalize_domain(topic)
    if not domain:
        return {"items": None, "error": "invalid_topic"}

    url = f"{BASE_URL}/{domain}"

    raw = paid_api._fetch_raw(
        url,
        method="GET",
        body=None,
        params=None,
        auth=None,
        cache_key=None,
        cache_ttl_hours=0,
        user_agent_suffix="(trustpilot-adapter)",
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

    return {"items": {"domain": domain, "html": html}, "error": None}


def parse_trustpilot_response(
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

    domain = payload.get("domain") or ""
    html = payload.get("html") or ""
    if not html:
        return []

    # Extract JSON-LD script blocks
    json_ld_blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not json_ld_blocks:
        sys.stderr.write(
            "[trustpilot] no JSON-LD blocks found; Trustpilot may have changed layout\n"
        )
        return []

    # Find the first JSON-LD block that contains reviews
    review_list: list[dict[str, Any]] = []
    aggregate_rating = 0.0
    aggregate_count = 0
    product_name = domain

    for block in json_ld_blocks:
        try:
            data = json.loads(block.strip())
        except (ValueError, json.JSONDecodeError):
            continue
        # Could be dict or list
        candidates = data if isinstance(data, list) else [data]
        for c in candidates:
            if not isinstance(c, dict):
                continue
            if c.get("@type") == "Organization" or c.get("@type") == "LocalBusiness":
                name = c.get("name")
                if name:
                    product_name = str(name)
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
                embedded_reviews = c.get("review") or []
                if isinstance(embedded_reviews, list):
                    review_list.extend(r for r in embedded_reviews if isinstance(r, dict))
            elif c.get("@type") == "Review":
                review_list.append(c)

    if not review_list and aggregate_count == 0:
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    # If no individual reviews surfaced but aggregate data did, emit one summary item.
    if not review_list and aggregate_count > 0:
        item = reviews.build_review_item(
            item_id=f"trustpilot:{domain}:summary",
            platform="trustpilot",
            product_name=product_name,
            url=f"https://www.trustpilot.com/review/{domain}",
            source_domain="trustpilot.com",
            star_rating=aggregate_rating,
            review_count=aggregate_count,
            relevance=0.7,
            why_relevant=f"Trustpilot aggregate for {product_name}",
        )
        return [item]

    for i, r in enumerate(review_list[:limit]):
        if not isinstance(r, dict):
            continue
        rating_obj = r.get("reviewRating") or {}
        star_rating = 0.0
        if isinstance(rating_obj, dict):
            star_rating = rating_obj.get("ratingValue", 0)

        author_obj = r.get("author") or {}
        author_name = ""
        if isinstance(author_obj, dict):
            author_name = author_obj.get("name", "") or ""

        review_text = r.get("reviewBody") or r.get("description") or ""
        review_date_raw = r.get("datePublished") or r.get("dateCreated") or ""
        review_date = review_date_raw[:10] if review_date_raw else None

        review_id = r.get("@id") or f"{domain}-{i}"

        item = reviews.build_review_item(
            item_id=f"trustpilot:{review_id}",
            platform="trustpilot",
            product_name=product_name,
            url=f"https://www.trustpilot.com/review/{domain}",
            source_domain="trustpilot.com",
            star_rating=star_rating,
            review_count=aggregate_count,
            review_text=review_text,
            reviewer_id=author_name,
            review_date=review_date,
            author=author_name or None,
            relevance=0.7,
            why_relevant=f"Trustpilot review for {product_name}",
            extra_metadata={"domain": domain},
        )
        parsed.append(item)
    return parsed
