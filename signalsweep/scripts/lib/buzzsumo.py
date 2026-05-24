"""BuzzSumo content search — envelope-first (signalsweep 3.25.0+).

Endpoint: `api.buzzsumo.com/search/articles.json`. Requires `BUZZSUMO_API_KEY`.
v3.7 paid-APIs + creds.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

ENDPOINT = "https://api.buzzsumo.com/search/articles.json"


def search_buzzsumo(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = cfg.get("BUZZSUMO_API_KEY")
    if not api_key:
        return {"items": None, "error": "credentials_missing"}
    params = {"api_key": api_key, "q": topic, "num_results": 25}
    return paid_api.fetch_json(ENDPOINT, params=params)


def parse_buzzsumo_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    articles = response["items"].get("results") or []
    out = []
    for a in articles:
        url = a.get("url")
        if not url:
            continue
        out.append({
            "id": f"buzzsumo:{a.get('id', url)}",
            "title": (a.get("title") or "")[:200],
            "snippet": "",
            "url": url,
            "source_domain": a.get("domain_name") or "",
            "date": (a.get("published_date") or "")[:10],
            "relevance": 0.7,
            "why_relevant": f"BuzzSumo — {a.get('domain_name', 'article')}",
            "metadata": {
                "platform": "buzzsumo",
                "total_shares": a.get("total_shares", 0),
                "facebook_shares": a.get("facebook_shares", 0),
                "twitter_shares": a.get("twitter_shares", 0),
            },
        })
    return out
