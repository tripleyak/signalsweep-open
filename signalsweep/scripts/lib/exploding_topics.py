"""Exploding Topics emerging-trends API (signalsweep 3.9.0+).

Semrush-owned. Surfaces early-stage trending topics with growth-rate filter.
Paid (enterprise); ships with `credentials_missing` envelope when key absent.

Auth: `EXPLODING_TOPICS_API_KEY` (Bearer).
Endpoint base: verify at implementation; may be enterprise-sales-only.
"""

from __future__ import annotations

from typing import Any

from . import demand_signals


SEARCH_URL = "https://api.explodingtopics.com/v1/topics"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_exploding_topics(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not demand_signals.is_demand_signals_enabled(config):
        return demand_signals.disabled_envelope()

    api_key = config.get("EXPLODING_TOPICS_API_KEY") or ""
    if not api_key:
        return demand_signals.credentials_missing_envelope()

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {"q": topic, "limit": limit}
    result = demand_signals.fetch_trends_json(
        SEARCH_URL,
        params=params,
        bearer_token=api_key,
        cache_key=f"exploding_topics:{topic}:{depth}",
        user_agent_suffix="(exploding_topics-adapter)",
    )
    err = result.get("error") or ""
    if isinstance(err, str) and ("401" in err or "403" in err):
        return demand_signals.credentials_invalid_envelope()
    return result


def parse_exploding_topics_response(
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

    topics = payload.get("topics") or payload.get("results") or []
    if not isinstance(topics, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for entry in topics[:limit]:
        if not isinstance(entry, dict):
            continue
        name = (entry.get("name") or entry.get("topic") or "").strip()
        if not name:
            continue
        growth = entry.get("growth") or entry.get("growth_rate") or 0
        try:
            growth_num = float(growth) if growth is not None else 0.0
        except (TypeError, ValueError):
            growth_num = 0.0
        parsed.append(
            demand_signals.build_trend_item(
                item_id=f"exploding:{name[:60]}",
                title=name,
                snippet=f"Exploding Topics — growth {growth_num:+.1f}%",
                url=entry.get("url") or f"https://explodingtopics.com/topic/{name.replace(' ', '-').lower()}",
                source_domain="explodingtopics.com",
                relevance=0.7,
                why_relevant=f"Emerging trend: {name[:60]}",
                engagement_score=growth_num,
                date=to_date or None,
                metadata={"growth_rate": growth_num, "category": entry.get("category", "")},
            )
        )
    return parsed
