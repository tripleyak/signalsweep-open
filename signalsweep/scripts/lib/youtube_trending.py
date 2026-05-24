"""YouTube Trending via Data API v3 (signalsweep 3.9.0+).

Free tier (API key). YouTube Data API v3 `videos.list?chart=mostPopular`
surfaces region-specific trending videos with view/like/comment counts.

Auth: `YOUTUBE_API_KEY` (free — create at console.cloud.google.com).
Region: `YOUTUBE_TRENDING_REGION` (ISO-3166-1 alpha-2, default "US").
Quota: 1 unit per videos.list call; free tier = 10,000/day.

Ships with `credentials_missing` envelope when key absent (v3.7 pattern).
"""

from __future__ import annotations

from typing import Any

from . import demand_signals


SEARCH_URL = "https://www.googleapis.com/youtube/v3/videos"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}

DEFAULT_REGION = "US"


def search_youtube_trending(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not demand_signals.is_demand_signals_enabled(config):
        return demand_signals.disabled_envelope()

    api_key = config.get("YOUTUBE_API_KEY") or ""
    if not api_key:
        return demand_signals.credentials_missing_envelope()

    region = (config.get("YOUTUBE_TRENDING_REGION") or DEFAULT_REGION).upper()
    max_results = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": region,
        "maxResults": max_results,
        "key": api_key,
    }
    result = demand_signals.fetch_trends_json(
        SEARCH_URL,
        params=params,
        cache_key=f"youtube_trending:{region}:{depth}",
        user_agent_suffix="(youtube_trending-adapter)",
    )

    # Map common YouTube error conditions to explicit envelopes.
    err = result.get("error") or ""
    if isinstance(err, str):
        if "403" in err or "quotaExceeded" in err:
            return demand_signals.rate_limited_envelope()
        if "401" in err or "invalidKey" in err:
            return demand_signals.credentials_invalid_envelope()
    return result


def parse_youtube_trending_response(
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

    videos = payload.get("items") or []
    if not isinstance(videos, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed: list[dict[str, Any]] = []
    for video in videos[:limit]:
        if not isinstance(video, dict):
            continue
        video_id = video.get("id") or ""
        snippet = video.get("snippet") or {}
        stats = video.get("statistics") or {}

        title = (snippet.get("title") or "").strip()
        if not title or not video_id:
            continue

        description = (snippet.get("description") or "").strip()
        channel = (snippet.get("channelTitle") or "").strip()
        published = snippet.get("publishedAt") or ""
        date = published[:10] if len(published) >= 10 else None

        try:
            view_count = int(stats.get("viewCount") or 0)
        except (TypeError, ValueError):
            view_count = 0
        try:
            like_count = int(stats.get("likeCount") or 0)
        except (TypeError, ValueError):
            like_count = 0

        region = (snippet.get("defaultAudioLanguage") or "").upper()

        parsed.append(
            demand_signals.build_trend_item(
                item_id=f"yt_trending:{video_id}",
                title=title,
                snippet=description[:500],
                url=f"https://www.youtube.com/watch?v={video_id}",
                source_domain="youtube.com",
                relevance=0.7,
                why_relevant=f"YouTube trending: {title[:60]}",
                engagement_score=float(view_count),
                date=date,
                author=channel or None,
                metadata={
                    "video_id": video_id,
                    "channel": channel,
                    "view_count": view_count,
                    "like_count": like_count,
                    "region": region or query,
                },
            )
        )
    return parsed
