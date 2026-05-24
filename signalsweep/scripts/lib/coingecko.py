"""CoinGecko — crypto market prices + tokens (signalsweep 3.22.0+).

Endpoint: `api.coingecko.com/api/v3/search`. Free tier no auth; demo
API key `COINGECKO_API_KEY` (if set) sent as `x-cg-demo-api-key` header.

v3.6 public-APIs tier.
"""

from __future__ import annotations

from typing import Any

from . import public_api

ENDPOINT = "https://api.coingecko.com/api/v3/search"


def search_coingecko(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not public_api.is_public_apis_enabled(cfg):
        return {"items": None, "error": "public_apis_disabled"}
    api_key = cfg.get("COINGECKO_API_KEY")
    extra_headers = {"x-cg-demo-api-key": api_key} if api_key else None
    return public_api.fetch_json(
        ENDPOINT,
        params={"query": topic},
        extra_headers=extra_headers,
        user_agent_suffix="coingecko-adapter",
    )


def parse_coingecko_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    coins = response["items"].get("coins") or []
    out = []
    for c in coins[:25]:
        cid = c.get("id")
        if not cid:
            continue
        out.append({
            "id": f"coingecko:{cid}",
            "title": f"{c.get('symbol', cid).upper()} — {c.get('name') or cid}",
            "snippet": f"Market cap rank: {c.get('market_cap_rank', 'n/a')}",
            "url": f"https://www.coingecko.com/en/coins/{cid}",
            "source_domain": "coingecko.com",
            "date": None,
            "relevance": 0.7,
            "why_relevant": f"CoinGecko — {c.get('name') or cid}",
            "metadata": {
                "platform": "coingecko",
                "coin_id": cid,
                "symbol": (c.get("symbol") or "").upper(),
                "market_cap_rank": c.get("market_cap_rank"),
                "thumb": c.get("thumb"),
            },
        })
    return out
