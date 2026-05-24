"""Polygon.io — market data for equities, options, forex, crypto (signalsweep 3.18.0+).

Free tier: 5 req/minute. Paid tiers unlock real-time + higher throughput.
Endpoint: `api.polygon.io/v3/reference/tickers` (search by name).

Requires `POLYGON_API_KEY`. Gated by v3.7 paid-APIs + creds.
"""

from __future__ import annotations

from typing import Any

from . import financial_markets, paid_api

ENDPOINT = "https://api.polygon.io/v3/reference/tickers"
DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_polygon_io(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = cfg.get("POLYGON_API_KEY")
    if not api_key:
        return {"items": None, "error": "credentials_missing"}
    limit = DEPTH_LIMITS.get(depth, 25)
    params = {
        "search": topic,
        "active": "true",
        "limit": limit,
        "apiKey": api_key,
    }
    return paid_api.fetch_json(ENDPOINT, params=params)


def parse_polygon_io_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    tickers = response["items"].get("results") or []
    results = []
    for t in tickers:
        ticker = t.get("ticker") or ""
        if not ticker:
            continue
        results.append(financial_markets.build_financial_item(
            item_id=f"polygon:{ticker}",
            platform="polygon_io",
            title=f"{ticker} — {t.get('name') or ticker}",
            snippet=f"{t.get('market') or ''} · {t.get('type') or ''} · {t.get('primary_exchange') or ''}".strip(" ·"),
            url=f"https://polygon.io/quote/{ticker}",
            source_domain="polygon.io",
            asset_type=t.get("type", "").lower() or "equity",
            symbol=ticker,
            exchange=t.get("primary_exchange", ""),
            currency=t.get("currency_name", ""),
            last_updated=t.get("last_updated_utc", "").split("T")[0] or None,
            relevance=0.7,
            why_relevant=f"Polygon.io ticker {ticker} ({(t.get('name') or '')[:40]})",
            extra_metadata={
                "market": t.get("market", ""),
                "locale": t.get("locale", ""),
                "cik": t.get("cik", ""),
            },
        ))
    return results
