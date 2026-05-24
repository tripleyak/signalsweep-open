"""Google News RSS (signalsweep 3.20.0+).

Public RSS feed at `news.google.com/rss/search?q={query}`. No auth.
Graceful-degrade parser (XML via ElementTree). Gated by v3.6 public-APIs.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus

from . import public_api

ENDPOINT = "https://news.google.com/rss/search"
DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_google_news(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not public_api.is_public_apis_enabled(cfg):
        return {"items": None, "error": "public_apis_disabled"}
    params = {
        "q": topic,
        "hl": cfg.get("GOOGLE_NEWS_LANG", "en-US"),
        "gl": cfg.get("GOOGLE_NEWS_COUNTRY", "US"),
        "ceid": f"{cfg.get('GOOGLE_NEWS_COUNTRY', 'US')}:{cfg.get('GOOGLE_NEWS_LANG', 'en').split('-')[0]}",
    }
    return public_api.fetch_xml(
        ENDPOINT,
        params=params,
        user_agent_suffix="google-news-adapter",
    )


def _extract_source_domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)/", url or "")
    return (m.group(1) if m else "").replace("www.", "")


def parse_google_news_response(response: dict[str, Any], depth: str = "default") -> list[dict[str, Any]]:
    if response.get("error"):
        return []
    root = response.get("items")
    if root is None:
        return []
    # public_api.fetch_xml returns the parsed Element directly
    try:
        channel = root.find("channel")
        items = channel.findall("item") if channel is not None else []
    except AttributeError:
        return []
    limit = DEPTH_LIMITS.get(depth, 25)
    out = []
    for item in items[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        description = (item.findtext("description") or "").strip()
        source_el = item.find("source")
        source_name = (source_el.text if source_el is not None and source_el.text else "").strip()
        domain = _extract_source_domain(link)
        if not link:
            continue
        out.append({
            "id": f"google_news:{link}",
            "title": title[:200],
            "snippet": description[:500],
            "url": link,
            "source_domain": domain or "news.google.com",
            "date": pub_date[:16] if pub_date else None,
            "relevance": 0.65,
            "why_relevant": f"Google News article from {source_name or domain}",
            "metadata": {
                "platform": "google_news",
                "publisher": source_name,
                "pub_date_raw": pub_date,
            },
        })
    return out
