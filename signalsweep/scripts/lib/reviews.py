"""Shared review-item normalization helper (signalsweep 3.17.0+).

Consumed by the 6 v3.17 review-aggregation adapters:
- trustpilot, g2, capterra, app_store_reviews, google_play_reviews, yelp_fusion

Parallels `demand_signals.py` (v3.9) and `marketplace_oauth.py` (v3.14)
helper-module pattern: one module exports one primary builder function used
by sibling adapters for consistent item shape.

`build_review_item(...)` enforces:
- star_rating is a float 0-5 (coerce + clamp; 0.0 on failure)
- title ≤ 200 chars, review_text ≤ 500 chars
- metadata dict includes all review-specific fields for downstream
  clustering/fusion access

All 6 adapters emit items with consistent `metadata` keys:
  star_rating (float 0-5)
  review_count (int — aggregate for product/business when surfaced)
  reviewer_id (platform ID or anonymized hash)
  verified_purchase (bool, when platform surfaces)
  helpful_votes (int, when platform surfaces)
  review_date (ISO date string)
  platform (str — e.g., "trustpilot", "g2")
"""

from __future__ import annotations

from typing import Any


def _coerce_rating(raw: Any) -> float:
    """Coerce arbitrary input to float 0-5. Return 0.0 on any failure."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    # Clamp to 0-5
    if value < 0:
        return 0.0
    if value > 5:
        return 5.0
    return value


def build_review_item(
    *,
    item_id: str,
    platform: str,
    product_name: str,
    url: str,
    source_domain: str,
    star_rating: Any = 0.0,
    review_count: int = 0,
    review_text: str = "",
    reviewer_id: str = "",
    verified_purchase: bool = False,
    helpful_votes: int = 0,
    review_date: str | None = None,
    author: str | None = None,
    relevance: float = 0.65,
    why_relevant: str = "",
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a signalsweep-standard item dict from review fields.

    Consumers: trustpilot, g2, capterra, app_store_reviews, google_play_reviews,
    yelp_fusion.
    """
    rating = _coerce_rating(star_rating)
    text = (review_text or "")[:500]

    # Title: use product_name + rating summary, truncated.
    title_pieces = [product_name]
    if rating > 0:
        title_pieces.append(f"★ {rating:.1f}")
    if review_count:
        title_pieces.append(f"({review_count:,} reviews)")
    title = " · ".join(title_pieces)[:200]

    snippet = text or f"{platform.title()} review"
    if rating > 0 and review_count and not text:
        snippet = f"{rating:.1f}★ avg across {review_count:,} reviews"
    snippet = snippet[:500]

    metadata: dict[str, Any] = {
        "platform": platform,
        "star_rating": rating,
        "review_count": int(review_count) if review_count else 0,
        "reviewer_id": reviewer_id,
        "verified_purchase": bool(verified_purchase),
        "helpful_votes": int(helpful_votes) if helpful_votes else 0,
        "review_date": review_date or "",
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    item: dict[str, Any] = {
        "id": item_id,
        "title": title,
        "snippet": snippet,
        "url": url,
        "source_domain": source_domain,
        "date": review_date,
        "relevance": relevance,
        "why_relevant": why_relevant or f"{platform.title()} review for {product_name[:60]}",
        "metadata": metadata,
    }
    if author:
        item["author"] = author

    return item
