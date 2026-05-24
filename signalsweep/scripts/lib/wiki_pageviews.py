"""Wikipedia Pageviews API (signalsweep 3.6+).

No auth. Daily page view counts for a Wikipedia article.

Flow:
  1. Resolve topic → article title via en.wikipedia.org/w/api.php (opensearch).
  2. Fetch daily series via wikimedia.org/api/rest_v1 pageviews endpoint.
  3. Produce a single aggregate item summarizing avg/peak/trend.
"""

from __future__ import annotations

from typing import Any

from . import public_api


OPENSEARCH_URL = "https://en.wikipedia.org/w/api.php"
PAGEVIEWS_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "en.wikipedia/all-access/user/{title}/daily/{from_ymd}/{to_ymd}"
)


def _resolve_title(topic: str) -> str | None:
    params = {
        "action": "opensearch",
        "search": topic,
        "limit": 1,
        "namespace": 0,
        "format": "json",
    }
    result = public_api.fetch_json(
        OPENSEARCH_URL, params=params,
        cache_key=f"wiki-opensearch:{topic}",
        user_agent_suffix="(wiki-pageviews-adapter)",
    )
    if result.get("error") or not result.get("items"):
        return None
    # opensearch returns [query, [titles], [descriptions], [urls]]
    payload = result["items"]
    if isinstance(payload, list) and len(payload) >= 2 and payload[1]:
        return payload[1][0]
    return None


def search_wiki_pageviews(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    title = _resolve_title(topic)
    if not title:
        return {"items": {"title": None, "series": []}, "error": None}

    from_ymd = (from_date or "").replace("-", "")
    to_ymd = (to_date or "").replace("-", "")
    if not from_ymd or not to_ymd:
        return {"items": {"title": title, "series": []}, "error": None}

    url = PAGEVIEWS_URL.format(
        title=title.replace(" ", "_"),
        from_ymd=from_ymd,
        to_ymd=to_ymd,
    )
    result = public_api.fetch_json(
        url,
        cache_key=f"wiki-pageviews:{title}:{from_ymd}:{to_ymd}",
        user_agent_suffix="(wiki-pageviews-adapter)",
    )
    if result.get("error"):
        return {"items": {"title": title, "series": []}, "error": result["error"]}

    series = (result.get("items") or {}).get("items") or []
    return {"items": {"title": title, "series": series}, "error": None}


def parse_wiki_pageviews_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    payload = response["items"]
    title = payload.get("title") or ""
    series = payload.get("series") or []

    if not title or not series:
        return []

    daily_views = [(s.get("timestamp") or "", s.get("views") or 0) for s in series]
    views_only = [v for _, v in daily_views if isinstance(v, int)]
    if not views_only:
        return []

    total = sum(views_only)
    avg = total / len(views_only) if views_only else 0
    peak_idx = views_only.index(max(views_only))
    peak_ts = daily_views[peak_idx][0]
    peak_date = (
        f"{peak_ts[:4]}-{peak_ts[4:6]}-{peak_ts[6:8]}"
        if peak_ts and len(peak_ts) >= 8 else None
    )

    article_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
    body = (
        f"Wikipedia pageviews for '{title}' from {from_date} to {to_date}: "
        f"{total:,} total views, {int(avg):,} average daily, "
        f"peak on {peak_date} with {max(views_only):,} views."
    )

    return [{
        "item_id": f"wiki_pv:{title}",
        "source": "wiki_pageviews",
        "title": f"Wikipedia pageviews: {title}",
        "body": body,
        "url": article_url,
        "author": None,
        "container": "en.wikipedia.org",
        "published_at": to_date or None,
        "engagement": {"total_views": total, "avg_daily": int(avg)},
        "relevance_hint": 0.7,
        "why_relevant": f"Interest signal for '{title}' via Wikipedia pageviews",
        "metadata": {
            "article_title": title,
            "daily_series": daily_views,
            "avg_daily_views": int(avg),
            "peak_date": peak_date,
            "peak_views": max(views_only),
            "total_views": total,
            "data_points": len(views_only),
        },
    }]
