"""SparkToro audience research (signalsweep 3.9.0+).

SparkToro surfaces audience-overlap data: what podcasts, YouTube channels,
publications, and accounts the audience of a given topic/brand also
consumes. Paid API; ships with `credentials_missing` envelope when key absent.

Auth: `SPARKTORO_API_KEY` (Bearer).
Endpoint base: https://api.sparktoro.com/v1 (verify at implementation; may be
enterprise-sales-only — if so, adapter ships as permanent envelope).
"""

from __future__ import annotations

from typing import Any

from . import demand_signals


SEARCH_URL = "https://api.sparktoro.com/v1/search"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_sparktoro(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not demand_signals.is_demand_signals_enabled(config):
        return demand_signals.disabled_envelope()

    api_key = config.get("SPARKTORO_API_KEY") or ""
    if not api_key:
        return demand_signals.credentials_missing_envelope()

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {"query": topic, "limit": limit}
    result = demand_signals.fetch_trends_json(
        SEARCH_URL,
        params=params,
        bearer_token=api_key,
        cache_key=f"sparktoro:{topic}:{depth}",
        user_agent_suffix="(sparktoro-adapter)",
    )
    err = result.get("error") or ""
    if isinstance(err, str) and ("401" in err or "403" in err):
        return demand_signals.credentials_invalid_envelope()
    return result


def parse_sparktoro_response(
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

    audiences = payload.get("audiences") or payload.get("results") or []
    if not isinstance(audiences, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for entry in audiences[:limit]:
        if not isinstance(entry, dict):
            continue
        name = (entry.get("name") or entry.get("title") or "").strip()
        if not name:
            continue
        overlap = entry.get("overlap_score") or entry.get("score") or 0
        try:
            overlap_num = float(overlap) if overlap is not None else 0.0
        except (TypeError, ValueError):
            overlap_num = 0.0
        parsed.append(
            demand_signals.build_trend_item(
                item_id=f"sparktoro:{name[:60]}",
                title=name,
                snippet=(entry.get("description") or f"Audience overlap: {overlap_num:.1f}")[:500],
                url=entry.get("url") or f"https://sparktoro.com/search?q={query}",
                source_domain="sparktoro.com",
                relevance=0.7,
                why_relevant=f"SparkToro audience overlap: {name[:60]}",
                engagement_score=overlap_num,
                date=to_date or None,
                metadata={"overlap_score": overlap_num, "type": entry.get("type", "")},
            )
        )
    return parsed
