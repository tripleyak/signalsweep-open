"""Amazon Reviews search via ScrapeCreators (signalsweep 3.7+).

Given an ASIN or product query, ScrapeCreators returns recent Amazon reviews
with star rating, review body, author, and date.

Auth: reuses `SCRAPECREATORS_API_KEY` (already set in user's env for v3.5
sources like linkedin/x_sc).

Mirrors `scripts/lib/linkedin.py` structure — same SC auth pattern, same
error-wrapping style. Cache via `paid_api`'s 12h TTL is not used here;
ScrapeCreators responses are fresh per-call.
"""

from __future__ import annotations

import math
import sys
from typing import Any, Dict, List

from . import http

SCRAPECREATORS_URL = "https://api.scrapecreators.com/v1/amazon/reviews"

DEPTH_CONFIG = {
    "quick": 10,
    "default": 25,
    "deep": 50,
}


def _log(msg: str) -> None:
    if sys.stderr.isatty():
        sys.stderr.write(f"[AmzRev] {msg}\n")
        sys.stderr.flush()


def search_amazon_reviews(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    api_key: str = "",
) -> Dict[str, Any]:
    """Search Amazon reviews for products matching topic.

    `topic` may be an ASIN (e.g., `B08PICKLE1`) or a free-text product query.
    Returns `{"reviews": [...], "error": None|str}`.
    """
    if not api_key:
        return {"reviews": [], "error": "SCRAPECREATORS_API_KEY required for Amazon Reviews"}

    count = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])
    headers = http.scrapecreators_headers(api_key)
    payload = {
        "query": topic,
        "limit": count,
        "sort_by": "recent",
    }

    try:
        response = http.post(SCRAPECREATORS_URL, payload, headers=headers, timeout=30)
    except Exception as e:
        _log(f"ScrapeCreators Amazon Reviews failed: {e}")
        msg = str(e)
        if any(code in msg for code in ("402", "403", "429", "500", "502", "503")):
            msg = "ScrapeCreators unavailable — visit scrapecreators.com to check status"
        return {"reviews": [], "error": msg}

    reviews = response.get("data", response.get("reviews", response.get("results", [])))
    if isinstance(reviews, dict):
        reviews = reviews.get("reviews", reviews.get("results", []))
    if not isinstance(reviews, list):
        reviews = []

    _log(f"Found {len(reviews)} reviews")
    return {"reviews": reviews}


def parse_amazon_reviews_response(
    response: Dict[str, Any],
    query: str = "",
) -> List[Dict[str, Any]]:
    """Parse Amazon reviews response into normalized item dicts."""
    reviews = response.get("reviews", [])
    parsed = []

    for i, review in enumerate(reviews):
        if not isinstance(review, dict):
            continue
        body = (review.get("body", "") or
                review.get("text", "") or
                review.get("content", "") or "").strip()
        title = (review.get("title", "") or "").strip()
        asin = review.get("asin", "") or ""
        author = (review.get("author", "") or review.get("reviewer", "") or "").strip()
        if isinstance(author, dict):
            author = (author.get("name") or "").strip()
        rating = review.get("rating") or review.get("stars") or review.get("score")
        verified = review.get("verified_purchase") or review.get("verified", False)
        helpful_count = review.get("helpful_count") or review.get("helpful", 0)

        date_str = review.get("date") or review.get("reviewed_at") or review.get("created_at") or ""
        if date_str and len(date_str) >= 10:
            date_str = date_str[:10]
        else:
            date_str = None

        url = review.get("url") or (f"https://www.amazon.com/dp/{asin}" if asin else "")

        if not body and not title:
            continue

        rank_score = max(0.3, 1.0 - (i * 0.03))
        helpful_boost = min(0.15, math.log1p(helpful_count or 0) / 15)
        rating_boost = 0.05 if rating and rating >= 4 else 0
        relevance = min(1.0, rank_score + helpful_boost + rating_boost)

        effective_title = title or body[:100]

        parsed.append({
            "id": review.get("id") or f"AR{i + 1}",
            "title": effective_title,
            "snippet": body[:400],
            "url": url,
            "source_domain": "amazon.com",
            "date": date_str,
            "relevance": round(relevance, 2),
            "why_relevant": f"Amazon review ({rating}★)" if rating else "Amazon review",
            "metadata": {
                "asin": asin,
                "author": author,
                "rating": rating,
                "verified_purchase": bool(verified),
                "helpful_count": helpful_count or 0,
            },
        })

    return parsed
