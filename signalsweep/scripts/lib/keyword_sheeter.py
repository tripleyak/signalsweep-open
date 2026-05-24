"""Keyword Sheeter bulk keyword expansion (signalsweep 3.9.0+).

Keyword Sheeter wraps Google autocomplete with bulk prefix/suffix
expansion — given a seed query, it returns dozens of long-tail keyword
variants. Free public tool.

No auth required. Endpoint shape may drift.

Endpoint: https://keywordsheeter.com/api/search
"""

from __future__ import annotations

from typing import Any

from . import demand_signals


SEARCH_URL = "https://keywordsheeter.com/api/search"

DEPTH_LIMITS = {"quick": 20, "default": 50, "deep": 100}


def search_keyword_sheeter(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not demand_signals.is_demand_signals_enabled(config):
        return demand_signals.disabled_envelope()

    params = {"q": topic}
    return demand_signals.fetch_trends_json(
        SEARCH_URL,
        params=params,
        cache_key=f"keyword_sheeter:{topic}:{depth}",
        user_agent_suffix="(keyword_sheeter-adapter)",
    )


def parse_keyword_sheeter_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    payload = response["items"]
    # Expected shapes: {"keywords": [...]} or {"results": [...]} or plain list.
    if isinstance(payload, dict):
        keywords = payload.get("keywords") or payload.get("results") or []
    elif isinstance(payload, list):
        keywords = payload
    else:
        return []

    if not isinstance(keywords, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for kw in keywords[:limit]:
        kw_text = kw if isinstance(kw, str) else (kw.get("keyword") if isinstance(kw, dict) else None)
        if not kw_text or not isinstance(kw_text, str):
            continue
        kw_text = kw_text.strip()
        if not kw_text:
            continue
        parsed.append(
            demand_signals.build_trend_item(
                item_id=f"sheeter:{kw_text[:60]}",
                title=kw_text,
                snippet="Google autocomplete expansion",
                url=f"https://keywordsheeter.com/?q={query}",
                source_domain="keywordsheeter.com",
                relevance=0.55,
                why_relevant=f"Long-tail keyword: {kw_text[:60]}",
                date=to_date or None,
                metadata={"query": query},
            )
        )
    return parsed
