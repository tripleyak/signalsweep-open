"""Pinterest Trends (signalsweep 3.9.0+).

Pinterest's advertiser-facing Trends tool surfaces top trending searches
by region + category. No auth required for public queries.

TOS basis: Pinterest Trends is publicly surfaced for advertiser research.

Endpoint: https://trends.pinterest.com/top-trends/ (base; reverse-engineered)
"""

from __future__ import annotations

from typing import Any

from . import demand_signals


SEARCH_URL = "https://trends.pinterest.com/api/v1/top-trends/"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}

DEFAULT_REGION = "US"

# Demand modifiers appended at deep depth to capture aspirational/lifestyle intent.
DEEP_MODIFIERS = ["ideas", "aesthetic"]


def _derive_trend_direction(growth_num: float) -> str:
    """Derive directional label from growth percentage."""
    if growth_num > 5:
        return "rising"
    if growth_num < -5:
        return "falling"
    return "stable"


def search_pinterest_trends(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not demand_signals.is_demand_signals_enabled(config):
        return demand_signals.disabled_envelope()

    region = (config.get("PINTEREST_TRENDS_REGION") or DEFAULT_REGION).upper()
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {
        "region": region,
        "trend_type": "growing",
        "limit": limit,
    }
    primary = demand_signals.fetch_trends_json(
        SEARCH_URL,
        params=params,
        cache_key=f"pinterest_trends:{region}:{depth}",
        user_agent_suffix="(pinterest_trends-adapter)",
    )

    if depth != "deep":
        return primary

    # At deep depth, fire additional modifier queries and merge results.
    modifier_responses: list[dict[str, Any]] = [primary]
    for mod in DEEP_MODIFIERS:
        mod_params = dict(params)
        mod_params["q"] = f"{topic} {mod}"
        resp = demand_signals.fetch_trends_json(
            SEARCH_URL,
            params=mod_params,
            cache_key=f"pinterest_trends:{region}:deep:{mod}",
            user_agent_suffix="(pinterest_trends-adapter)",
        )
        modifier_responses.append(resp)

    return _merge_trend_responses(modifier_responses)


def _merge_trend_responses(responses: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge multiple API responses, deduplicating trends by term."""
    seen: set[str] = set()
    merged_trends: list[dict[str, Any]] = []
    for resp in responses:
        items = resp.get("items")
        if not isinstance(items, dict):
            continue
        trends = items.get("trends") or items.get("results") or items.get("data") or []
        if not isinstance(trends, list):
            continue
        for entry in trends:
            if not isinstance(entry, dict):
                continue
            term = (
                entry.get("trend") or entry.get("keyword") or entry.get("query") or ""
            ).strip().lower()
            if term and term not in seen:
                seen.add(term)
                merged_trends.append(entry)
    return {"items": {"trends": merged_trends}, "error": None}


def parse_pinterest_trends_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
    region: str = DEFAULT_REGION,
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    payload = response["items"]
    if not isinstance(payload, dict):
        return []

    trends = payload.get("trends") or payload.get("results") or payload.get("data") or []
    if not isinstance(trends, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    tokens = {t.strip().lower() for t in query.split() if len(t.strip()) >= 3}

    parsed = []
    for entry in trends[:limit * 2]:  # fetch extra, filter
        if not isinstance(entry, dict):
            continue
        term = (entry.get("trend") or entry.get("keyword") or entry.get("query") or "").strip()
        if not term:
            continue
        # Client-side query-relevance filter
        if tokens and not any(tok in term.lower() for tok in tokens):
            # Keep unmatched trends too — they surface adjacent interest
            pass
        growth = entry.get("growth") or entry.get("growth_pct") or entry.get("score") or 0
        try:
            growth_num = float(growth) if growth is not None else 0.0
        except (TypeError, ValueError):
            growth_num = 0.0

        trend_direction = _derive_trend_direction(growth_num)
        seasonal_peak = entry.get("seasonal_peak") or entry.get("peak_month") or None
        related_searches = (entry.get("related_trends") or entry.get("related") or [])[:10]
        category = entry.get("category") or entry.get("taxonomy") or None

        snippet = f"Trending Pinterest search (+{growth_num:.0f}%)"
        if trend_direction == "falling":
            snippet = f"Pinterest search ({growth_num:.0f}%)"

        parsed.append(
            demand_signals.build_trend_item(
                item_id=f"pinterest_trend:{term[:60]}",
                title=term,
                snippet=snippet,
                url=f"https://pinterest.com/search/pins/?q={term.replace(' ', '+')}",
                source_domain="pinterest.com",
                relevance=0.65,
                why_relevant=f"Pinterest trending: {term[:60]}",
                engagement_score=growth_num,
                date=to_date or None,
                metadata={
                    "growth_pct": growth_num,
                    "region": region,
                    "trend_direction": trend_direction,
                    "seasonal_peak": seasonal_peak,
                    "related_searches": related_searches,
                    "category": category,
                },
            )
        )
        if len(parsed) >= limit:
            break
    return parsed
