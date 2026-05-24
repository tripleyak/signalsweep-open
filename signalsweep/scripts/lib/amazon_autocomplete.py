"""Amazon autocomplete multi-marketplace (signalsweep 3.9.0+).

Queries Amazon's public autocomplete endpoint per-marketplace and returns
suggestion lists across one or more Amazon storefronts. High-leverage for
Amazon PPC research — reveals live consumer search queries.

Endpoint (public, no auth):
  https://completion.amazon.com/api/2017/suggestions
  ?q=<term>&mid=<marketplace_id>&limit=11&alias=aps

Consumes v3.7.2 `amazon_marketplaces.py` for marketplace ID resolution.

Config:
  AMAZON_AUTOCOMPLETE_MARKETPLACES — comma-separated ISO codes (default: "US")
  SIGNALSWEEP_DISABLE_DEMAND_SIGNALS — master toggle
"""

from __future__ import annotations

from typing import Any

from . import amazon_marketplaces, demand_signals


SEARCH_URL = "https://completion.amazon.com/api/2017/suggestions"

DEPTH_LIMITS = {"quick": 5, "default": 11, "deep": 11}  # Amazon caps at ~11 regardless

POLITE_SLEEP_MS = 300  # Per-marketplace rate limiting


def _parse_marketplaces(config: dict[str, Any]) -> list[str]:
    raw = config.get("AMAZON_AUTOCOMPLETE_MARKETPLACES") or "US"
    codes = [c.strip().upper() for c in str(raw).split(",") if c.strip()]
    return codes or ["US"]


def search_amazon_autocomplete(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not demand_signals.is_demand_signals_enabled(config):
        return demand_signals.disabled_envelope()

    marketplaces = _parse_marketplaces(config)
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    results: list[dict[str, Any]] = []
    skipped: list[str] = []

    for code in marketplaces:
        marketplace = amazon_marketplaces.get_marketplace(code)
        if not marketplace:
            skipped.append(code)
            continue

        params = {
            "q": topic,
            "mid": marketplace["sp_api_marketplace_id"],
            "limit": limit,
            "alias": "aps",
        }
        result = demand_signals.fetch_trends_json(
            SEARCH_URL,
            params=params,
            cache_key=f"amazon_autocomplete:{code}:{topic}:{depth}",
            user_agent_suffix="(amazon_autocomplete-adapter)",
            polite_sleep_ms=POLITE_SLEEP_MS,
        )
        results.append({
            "marketplace": code,
            "country_name": marketplace.get("country_name", ""),
            "tld": marketplace.get("tld", ""),
            "response": result,
        })

    return {
        "items": {"results": results, "skipped": skipped},
        "error": None,
    }


def parse_amazon_autocomplete_response(
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

    results = payload.get("results") or []
    if not isinstance(results, list):
        return []

    parsed: list[dict[str, Any]] = []

    for entry in results:
        if not isinstance(entry, dict):
            continue
        marketplace = entry.get("marketplace", "")
        country = entry.get("country_name", "")
        tld = entry.get("tld", "com")
        resp = entry.get("response") or {}
        if resp.get("error") or not resp.get("items"):
            continue

        items_payload = resp["items"]
        # Amazon response shape: {"suggestions": [{"value": "...", ...}, ...]}
        if isinstance(items_payload, dict):
            suggestions = items_payload.get("suggestions") or []
        elif isinstance(items_payload, list):
            suggestions = items_payload
        else:
            continue

        if not isinstance(suggestions, list):
            continue

        for sug in suggestions:
            term = sug.get("value") if isinstance(sug, dict) else (sug if isinstance(sug, str) else None)
            if not term or not isinstance(term, str):
                continue
            term = term.strip()
            if not term:
                continue
            parsed.append(
                demand_signals.build_trend_item(
                    item_id=f"amazon_auto:{marketplace}:{term[:50]}",
                    title=term,
                    snippet=f"Amazon {country} autocomplete suggestion",
                    url=f"https://www.amazon.{tld}/s?k={term.replace(' ', '+')}",
                    source_domain=f"amazon.{tld}",
                    relevance=0.65,
                    why_relevant=f"Amazon {marketplace} buyer query: {term[:60]}",
                    date=to_date or None,
                    metadata={
                        "marketplace": marketplace,
                        "country_name": country,
                        "query": query,
                    },
                )
            )

    return parsed
