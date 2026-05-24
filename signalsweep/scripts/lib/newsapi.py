"""NewsAPI.org — global news aggregation (signalsweep 3.20.0+).

Endpoint: `newsapi.org/v2/everything?q=`. Free dev tier (100 req/day).
Requires `NEWSAPI_KEY`. Gated by v3.7 paid-APIs + creds.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

ENDPOINT = "https://newsapi.org/v2/everything"
DEPTH_LIMITS = {"quick": 15, "default": 50, "deep": 100}


def search_newsapi(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = cfg.get("NEWSAPI_KEY") or cfg.get("NEWS_API_KEY")
    if not api_key:
        return {"items": None, "error": "credentials_missing"}
    params = {
        "q": topic,
        "apiKey": api_key,
        "pageSize": DEPTH_LIMITS.get(depth, 50),
        "sortBy": cfg.get("NEWSAPI_SORT", "relevancy"),
    }
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    return paid_api.fetch_json(ENDPOINT, params=params)


def parse_newsapi_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    articles = response["items"].get("articles") or []
    out = []
    for a in articles:
        url = a.get("url") or ""
        if not url:
            continue
        source = (a.get("source") or {}).get("name") or ""
        out.append({
            "id": f"newsapi:{url}",
            "title": (a.get("title") or "")[:200],
            "snippet": (a.get("description") or "")[:500],
            "url": url,
            "source_domain": (a.get("source") or {}).get("id") or source.lower().replace(" ", "") or "newsapi.org",
            "date": (a.get("publishedAt") or "")[:10],
            "author": a.get("author"),
            "relevance": 0.68,
            "why_relevant": f"NewsAPI article from {source}",
            "metadata": {
                "platform": "newsapi",
                "publisher": source,
                "published_at": a.get("publishedAt"),
            },
        })
    return out
