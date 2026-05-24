"""Capterra SaaS review scrape (signalsweep 3.17.0+).

Fetches `capterra.com/p/{id}/{slug}/reviews/` HTML and parses embedded
JSON-LD review data. Gartner-owned; DOM is more stable than G2's but
still requires graceful parse.

Tier: v3.7 `SIGNALSWEEP_DISABLE_PAID_APIS`. No credentials. 500ms polite-sleep.

Topic: Capterra URL or `{id}/{slug}` path fragment.

Docs: capterra.com (DevTools).
"""

from __future__ import annotations

import json
import re
import sys
import time
from typing import Any

from . import paid_api, reviews


BASE_URL = "https://www.capterra.com/p"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}

POLITE_SLEEP_MS = 500


def _normalize_path(topic: str) -> str:
    t = topic.strip()
    for prefix in ("https://", "http://"):
        if t.startswith(prefix):
            t = t[len(prefix):]
    if t.startswith("www."):
        t = t[4:]
    if t.startswith("capterra.com/p/"):
        t = t[len("capterra.com/p/"):]
    if t.endswith("/reviews/"):
        t = t[:-len("/reviews/")]
    elif t.endswith("/reviews"):
        t = t[:-len("/reviews")]
    return t.rstrip("/")


def search_capterra(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}

    path = _normalize_path(topic)
    if not path:
        return {"items": None, "error": "invalid_topic"}

    url = f"{BASE_URL}/{path}/reviews/"

    raw = paid_api._fetch_raw(
        url, method="GET", body=None, params=None, auth=None,
        cache_key=None, cache_ttl_hours=0,
        user_agent_suffix="(capterra-adapter)",
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

    return {"items": {"path": path, "html": html}, "error": None}


def parse_capterra_response(
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

    path = payload.get("path") or ""
    html = payload.get("html") or ""
    if not html:
        return []

    json_ld_blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL,
    )
    if not json_ld_blocks:
        sys.stderr.write("[capterra] no JSON-LD blocks found; Capterra may have changed layout\n")
        return []

    review_list: list[dict[str, Any]] = []
    aggregate_rating = 0.0
    aggregate_count = 0
    # Capterra path shape: {id}/{slug} — use slug segment for display name
    product_name = (path.split("/", 1)[-1] if "/" in path else path).replace("-", " ").title()

    for block in json_ld_blocks:
        try:
            data = json.loads(block.strip())
        except (ValueError, json.JSONDecodeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for c in candidates:
            if not isinstance(c, dict):
                continue
            if c.get("@type") in ("SoftwareApplication", "Product"):
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
                embedded = c.get("review") or []
                if isinstance(embedded, list):
                    review_list.extend(r for r in embedded if isinstance(r, dict))
            elif c.get("@type") == "Review":
                review_list.append(c)

    if not review_list and aggregate_count == 0:
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    if not review_list and aggregate_count > 0:
        item = reviews.build_review_item(
            item_id=f"capterra:{path}:summary",
            platform="capterra",
            product_name=product_name,
            url=f"https://www.capterra.com/p/{path}/reviews/",
            source_domain="capterra.com",
            star_rating=aggregate_rating,
            review_count=aggregate_count,
            relevance=0.7,
            why_relevant=f"Capterra aggregate for {product_name}",
            extra_metadata={"path": path, "category": "saas"},
        )
        return [item]

    for i, r in enumerate(review_list[:limit]):
        if not isinstance(r, dict):
            continue
        rating_obj = r.get("reviewRating") or {}
        star_rating = rating_obj.get("ratingValue", 0) if isinstance(rating_obj, dict) else 0
        author_obj = r.get("author") or {}
        author_name = author_obj.get("name", "") if isinstance(author_obj, dict) else ""
        review_text = r.get("reviewBody") or r.get("description") or ""
        review_date_raw = r.get("datePublished") or r.get("dateCreated") or ""
        review_date = review_date_raw[:10] if review_date_raw else None
        review_id = r.get("@id") or f"{path}-{i}"

        item = reviews.build_review_item(
            item_id=f"capterra:{review_id}",
            platform="capterra",
            product_name=product_name,
            url=f"https://www.capterra.com/p/{path}/reviews/",
            source_domain="capterra.com",
            star_rating=star_rating,
            review_count=aggregate_count,
            review_text=review_text,
            reviewer_id=author_name,
            review_date=review_date,
            author=author_name or None,
            relevance=0.7,
            why_relevant=f"Capterra review for {product_name}",
            extra_metadata={"path": path, "category": "saas"},
        )
        parsed.append(item)
    return parsed
