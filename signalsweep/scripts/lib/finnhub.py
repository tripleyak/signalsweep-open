"""Finnhub — stock, forex, crypto market data + company fundamentals (signalsweep 3.18.0+).

Free tier: 60 req/min on core endpoints. Endpoint: `finnhub.io/api/v1/search`.

Requires `FINNHUB_API_KEY`. Gated by v3.7 paid-APIs + creds.
"""

from __future__ import annotations

from typing import Any

from . import financial_markets, paid_api

ENDPOINT = "https://finnhub.io/api/v1/search"


def search_finnhub(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = cfg.get("FINNHUB_API_KEY")
    if not api_key:
        return {"items": None, "error": "credentials_missing"}
    params = {"q": topic, "token": api_key}
    return paid_api.fetch_json(ENDPOINT, params=params)


def parse_finnhub_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    result = response["items"].get("result") or []
    out = []
    for t in result:
        symbol = t.get("symbol") or ""
        if not symbol:
            continue
        out.append(financial_markets.build_financial_item(
            item_id=f"finnhub:{symbol}",
            platform="finnhub",
            title=f"{symbol} — {t.get('description') or symbol}",
            snippet=f"{t.get('type') or ''} · {t.get('displaySymbol') or symbol}".strip(" ·"),
            url=f"https://finnhub.io/stock/{symbol}",
            source_domain="finnhub.io",
            asset_type=t.get("type", "").lower() or "equity",
            symbol=symbol,
            relevance=0.7,
            why_relevant=f"Finnhub {symbol} ({(t.get('description') or '')[:40]})",
            extra_metadata={
                "display_symbol": t.get("displaySymbol", ""),
            },
        ))
    return out
