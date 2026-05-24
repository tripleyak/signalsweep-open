"""AnswerThePublic question-demand API (signalsweep 3.9.0+).

Neil-Patel-owned. Visualizes question-phrased search demand. Paid API; ships
with `credentials_missing` envelope when key absent.

Auth: `ANSWERTHEPUBLIC_API_KEY` (Bearer).
Endpoint base: verify at implementation.
"""

from __future__ import annotations

from typing import Any

from . import demand_signals


SEARCH_URL = "https://api.answerthepublic.com/v1/search"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_answerthepublic(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not demand_signals.is_demand_signals_enabled(config):
        return demand_signals.disabled_envelope()

    api_key = config.get("ANSWERTHEPUBLIC_API_KEY") or ""
    if not api_key:
        return demand_signals.credentials_missing_envelope()

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {"q": topic, "language": "en", "limit": limit}
    result = demand_signals.fetch_trends_json(
        SEARCH_URL,
        params=params,
        bearer_token=api_key,
        cache_key=f"answerthepublic:{topic}:{depth}",
        user_agent_suffix="(answerthepublic-adapter)",
    )
    err = result.get("error") or ""
    if isinstance(err, str) and ("401" in err or "403" in err):
        return demand_signals.credentials_invalid_envelope()
    return result


def parse_answerthepublic_response(
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
        text = entry if isinstance(entry, str) else (entry.get("text") if isinstance(entry, dict) else None)
        if not text or not isinstance(text, str):
            continue
        text = text.strip()
        if not text:
            continue
        volume = 0
        category = ""
        if isinstance(entry, dict):
            try:
                volume = int(entry.get("volume") or 0)
            except (TypeError, ValueError):
                volume = 0
            category = entry.get("category") or entry.get("type") or ""
        parsed.append(
            demand_signals.build_trend_item(
                item_id=f"atp:{text[:50]}",
                title=text,
                snippet=f"AnswerThePublic question{f' [{category}]' if category else ''}",
                url=f"https://answerthepublic.com/reports/search?q={query.replace(' ', '+')}",
                source_domain="answerthepublic.com",
                relevance=0.65,
                why_relevant=f"Question demand: {text[:60]}",
                engagement_score=float(volume),
                date=to_date or None,
                metadata={"volume": volume, "category": category},
            )
        )
    return parsed
