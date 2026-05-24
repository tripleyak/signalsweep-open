"""FRED — Federal Reserve Economic Data (signalsweep 3.18.0+).

St. Louis Fed's FRED database covers 800k+ US and international economic
time series. Free with `FRED_API_KEY` (signup at fredaccount.stlouisfed.org).

Endpoint: `api.stlouisfed.org/fred/series/search` (JSON).
Gated by v3.7 `SIGNALSWEEP_DISABLE_PAID_APIS` + credential check (envelope
pattern matches v3.14/v3.15/v3.16 tiers).
"""

from __future__ import annotations

from typing import Any

from . import financial_markets, paid_api

ENDPOINT = "https://api.stlouisfed.org/fred/series/search"
DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_fred(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = cfg.get("FRED_API_KEY")
    if not api_key:
        return {"items": None, "error": "credentials_missing"}
    limit = DEPTH_LIMITS.get(depth, 25)
    params = {
        "search_text": topic,
        "api_key": api_key,
        "file_type": "json",
        "limit": limit,
    }
    return paid_api.fetch_json(ENDPOINT, params=params)


def parse_fred_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    seriess = response["items"].get("seriess") or []
    results = []
    for s in seriess:
        sid = s.get("id") or ""
        if not sid:
            continue
        results.append(financial_markets.build_financial_item(
            item_id=f"fred:{sid}",
            platform="fred",
            title=s.get("title") or sid,
            snippet=(s.get("notes") or "")[:300],
            url=f"https://fred.stlouisfed.org/series/{sid}",
            source_domain="fred.stlouisfed.org",
            asset_type="economic_indicator",
            symbol=sid,
            currency=s.get("units") or "",
            last_updated=s.get("last_updated", "").split(" ")[0] or None,
            relevance=0.7,
            why_relevant=f"FRED series {sid} — {(s.get('title') or '')[:60]}",
            extra_metadata={
                "frequency": s.get("frequency", ""),
                "seasonal_adjustment": s.get("seasonal_adjustment_short", ""),
                "observation_start": s.get("observation_start", ""),
                "observation_end": s.get("observation_end", ""),
            },
        ))
    return results
