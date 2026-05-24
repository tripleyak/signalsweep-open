"""TikTok Creative Center trending data (signalsweep 3.9.0+).

TikTok's advertiser-facing Creative Center surfaces trending hashtags,
songs, products, and creators. Publicly browsable.

**TOS boundary:** Creative Center is a public research tool intended for
advertisers. This adapter scrapes the documented JSON endpoints only (no
browser automation) and applies a conservative 500ms per-call rate limit.
Disable via SIGNALSWEEP_DISABLE_DEMAND_SIGNALS=1 if concerns arise.

Endpoint shape is reverse-engineered from DevTools Network tab; may drift.
"""

from __future__ import annotations

from typing import Any

from . import demand_signals


SEARCH_URL = "https://ads.tiktok.com/business/creativecenter/api/inspiration/hashtag/list"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}

DEFAULT_REGION = "US"
POLITE_SLEEP_MS = 500  # Conservative per-call delay (D6).


def search_tiktok_creative_center(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not demand_signals.is_demand_signals_enabled(config):
        return demand_signals.disabled_envelope()

    region = (config.get("TIKTOK_CC_REGION") or DEFAULT_REGION).upper()
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {
        "country_code": region,
        "period": 7,   # 7-day window default
        "page": 1,
        "limit": limit,
    }
    return demand_signals.fetch_trends_json(
        SEARCH_URL,
        params=params,
        cache_key=f"tiktok_cc:{region}:{depth}",
        user_agent_suffix="(tiktok_creative_center-adapter)",
        polite_sleep_ms=POLITE_SLEEP_MS,
    )


def parse_tiktok_creative_center_response(
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

    data = payload.get("data") or {}
    if not isinstance(data, dict):
        return []

    hashtags = data.get("list") or data.get("results") or []
    if not isinstance(hashtags, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for entry in hashtags[:limit]:
        if not isinstance(entry, dict):
            continue
        hashtag = (entry.get("hashtag_name") or entry.get("name") or entry.get("keyword") or "").strip()
        if not hashtag:
            continue
        if not hashtag.startswith("#"):
            hashtag = f"#{hashtag}"

        posts = entry.get("post_count") or entry.get("posts") or 0
        views = entry.get("video_views") or entry.get("views") or 0
        try:
            engagement = float(views or posts or 0)
        except (TypeError, ValueError):
            engagement = 0.0

        parsed.append(
            demand_signals.build_trend_item(
                item_id=f"tiktok_cc:{hashtag}",
                title=hashtag,
                snippet=f"TikTok trending hashtag — {posts} posts, {views} views",
                url=f"https://www.tiktok.com/tag/{hashtag.lstrip('#')}",
                source_domain="tiktok.com",
                relevance=0.65,
                why_relevant=f"TikTok Creative Center trending: {hashtag}",
                engagement_score=engagement,
                date=to_date or None,
                metadata={"posts": posts, "views": views, "region": "US"},
            )
        )
    return parsed
