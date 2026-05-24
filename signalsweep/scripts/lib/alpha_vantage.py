"""Alpha Vantage — equities, FX, crypto fundamentals (signalsweep 3.18.0+).

Free tier: 25 requests/day + API key. Paid tiers unlock higher throughput.
Endpoint: `www.alphavantage.co/query` with `function=SYMBOL_SEARCH`.

Requires `ALPHAVANTAGE_API_KEY`. Gated by v3.7 paid-APIs + creds.
"""

from __future__ import annotations

from typing import Any

from . import financial_markets, paid_api

ENDPOINT = "https://www.alphavantage.co/query"


def search_alpha_vantage(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = cfg.get("ALPHAVANTAGE_API_KEY") or cfg.get("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        return {"items": None, "error": "credentials_missing"}
    params = {
        "function": "SYMBOL_SEARCH",
        "keywords": topic,
        "apikey": api_key,
    }
    return paid_api.fetch_json(ENDPOINT, params=params)


def parse_alpha_vantage_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    matches = response["items"].get("bestMatches") or []
    results = []
    for m in matches:
        symbol = m.get("1. symbol") or ""
        if not symbol:
            continue
        results.append(financial_markets.build_financial_item(
            item_id=f"alphavantage:{symbol}",
            platform="alpha_vantage",
            title=f"{symbol} — {m.get('2. name') or symbol}",
            snippet=f"{m.get('3. type') or ''} · {m.get('4. region') or ''} · {m.get('8. currency') or ''}".strip(" ·"),
            url=f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}",
            source_domain="alphavantage.co",
            asset_type=m.get("3. type", "").lower() or "equity",
            symbol=symbol,
            exchange=m.get("4. region", ""),
            currency=m.get("8. currency", ""),
            relevance=0.7,
            why_relevant=f"Alpha Vantage symbol {symbol} ({m.get('2. name', '')[:40]})",
            extra_metadata={
                "market_open": m.get("5. marketOpen", ""),
                "market_close": m.get("6. marketClose", ""),
                "timezone": m.get("7. timezone", ""),
                "match_score": m.get("9. matchScore", ""),
            },
        ))
    return results
