"""Soovle multi-engine autocomplete (signalsweep 3.9.0+).

Soovle is a meta-search aggregator that queries 6 engines (Google, Bing,
YouTube, Wikipedia, Amazon, eBay) and returns their autocomplete
suggestions in a unified response.

No auth required. Public-facing research tool. Endpoint shape is
reverse-engineered from browser DevTools; may drift over time. Ships with
graceful-degrade parser that returns [] on unexpected shapes rather than
raising.

Endpoint: https://soovle.com/?q=<query>
"""

from __future__ import annotations

from typing import Any

from . import demand_signals


SEARCH_URL = "https://soovle.com/search"

# Soovle's 6 engines (as of 2026).
ENGINES = ("google", "bing", "youtube", "wikipedia", "amazon", "ebay")

DEPTH_LIMITS = {
    "quick": 6,     # 1 suggestion per engine
    "default": 30,  # 5 per engine
    "deep": 60,     # 10 per engine
}


def search_soovle(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch Soovle aggregated autocomplete suggestions for a topic."""
    config = config or {}
    if not demand_signals.is_demand_signals_enabled(config):
        return demand_signals.disabled_envelope()

    params = {"q": topic}
    return demand_signals.fetch_trends_json(
        SEARCH_URL,
        params=params,
        cache_key=f"soovle:{topic}",
        user_agent_suffix="(soovle-adapter)",
    )


def parse_soovle_response(
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

    # Soovle returns a dict keyed by engine with arrays of suggestions.
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    per_engine_limit = max(1, limit // len(ENGINES))

    parsed = []
    for engine in ENGINES:
        suggestions = payload.get(engine) or []
        if not isinstance(suggestions, list):
            continue
        for i, term in enumerate(suggestions[:per_engine_limit]):
            if not isinstance(term, str) or not term.strip():
                continue
            term = term.strip()
            parsed.append(
                demand_signals.build_trend_item(
                    item_id=f"soovle:{engine}:{i}:{term}",
                    title=term,
                    snippet=f"{engine.title()} autocomplete suggestion",
                    url=f"https://soovle.com/?q={query}",
                    source_domain="soovle.com",
                    relevance=0.55,
                    why_relevant=f"Soovle {engine} autocomplete: {term[:60]}",
                    date=to_date or None,
                    metadata={"engine": engine, "query": query},
                )
            )
            if len(parsed) >= limit:
                return parsed
    return parsed
