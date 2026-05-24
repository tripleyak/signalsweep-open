"""Glimpse emerging-trends API (signalsweep 3.9.0+).

Glimpse (meetglimpse.com) surfaces emerging search trends with growth-rate
filter. Chrome extension + API. Paid; ships with `credentials_missing`
envelope when key absent.

Auth: `GLIMPSE_API_KEY` (Bearer).
Endpoint base: verify at implementation.
"""

from __future__ import annotations

from typing import Any

from . import demand_signals


SEARCH_URL = "https://api.meetglimpse.com/v1/search"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_glimpse(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not demand_signals.is_demand_signals_enabled(config):
        return demand_signals.disabled_envelope()

    api_key = config.get("GLIMPSE_API_KEY") or ""
    if not api_key:
        return demand_signals.credentials_missing_envelope()

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {"q": topic, "limit": limit}
    result = demand_signals.fetch_trends_json(
        SEARCH_URL,
        params=params,
        bearer_token=api_key,
        cache_key=f"glimpse:{topic}:{depth}",
        user_agent_suffix="(glimpse-adapter)",
    )
    err = result.get("error") or ""
    if isinstance(err, str) and ("401" in err or "403" in err):
        return demand_signals.credentials_invalid_envelope()
    return result


def parse_glimpse_response(
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

    trends = payload.get("trends") or payload.get("results") or []
    if not isinstance(trends, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for entry in trends[:limit]:
        if not isinstance(entry, dict):
            continue
        name = (entry.get("keyword") or entry.get("term") or entry.get("name") or "").strip()
        if not name:
            continue
        growth = entry.get("growth") or entry.get("growth_rate") or 0
        volume = entry.get("volume") or entry.get("search_volume") or 0
        try:
            growth_num = float(growth) if growth is not None else 0.0
        except (TypeError, ValueError):
            growth_num = 0.0
        try:
            volume_num = int(volume) if volume is not None else 0
        except (TypeError, ValueError):
            volume_num = 0
        parsed.append(
            demand_signals.build_trend_item(
                item_id=f"glimpse:{name[:60]}",
                title=name,
                snippet=f"Glimpse emerging trend — {volume_num:,} searches/mo, {growth_num:+.0f}% growth",
                url=f"https://meetglimpse.com/trend/{name.replace(' ', '-').lower()}",
                source_domain="meetglimpse.com",
                relevance=0.7,
                why_relevant=f"Emerging trend: {name[:60]}",
                engagement_score=growth_num,
                date=to_date or None,
                metadata={"growth_rate": growth_num, "volume": volume_num},
            )
        )
    return parsed
