"""AlsoAsked "People Also Ask" demand (signalsweep 3.9.0+).

AlsoAsked surfaces Google's "People Also Ask" cluster — question-phrased
demand derived from SERP features. Paid API.

Auth: `ALSOASKED_API_KEY` (Bearer).
Endpoint base: verify at implementation.
"""

from __future__ import annotations

from typing import Any

from . import demand_signals


SEARCH_URL = "https://api.alsoasked.com/v1/search"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_alsoasked(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not demand_signals.is_demand_signals_enabled(config):
        return demand_signals.disabled_envelope()

    api_key = config.get("ALSOASKED_API_KEY") or ""
    if not api_key:
        return demand_signals.credentials_missing_envelope()

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {"term": topic, "depth": 2, "limit": limit}
    result = demand_signals.fetch_trends_json(
        SEARCH_URL,
        params=params,
        bearer_token=api_key,
        cache_key=f"alsoasked:{topic}:{depth}",
        user_agent_suffix="(alsoasked-adapter)",
    )
    err = result.get("error") or ""
    if isinstance(err, str) and ("401" in err or "403" in err):
        return demand_signals.credentials_invalid_envelope()
    return result


def parse_alsoasked_response(
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

    questions = payload.get("questions") or payload.get("results") or []
    if not isinstance(questions, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for entry in questions[:limit]:
        text = entry if isinstance(entry, str) else (entry.get("question") or entry.get("text") if isinstance(entry, dict) else None)
        if not text or not isinstance(text, str):
            continue
        text = text.strip()
        if not text:
            continue
        depth_level = 0
        if isinstance(entry, dict):
            try:
                depth_level = int(entry.get("depth") or 0)
            except (TypeError, ValueError):
                depth_level = 0
        parsed.append(
            demand_signals.build_trend_item(
                item_id=f"alsoasked:{text[:50]}",
                title=text,
                snippet="People Also Ask question",
                url=f"https://alsoasked.com/results?q={query.replace(' ', '+')}",
                source_domain="alsoasked.com",
                relevance=0.65,
                why_relevant=f"PAA question: {text[:60]}",
                date=to_date or None,
                metadata={"depth": depth_level},
            )
        )
    return parsed
