"""GDELT 2.0 — global events / news media DB (signalsweep 3.20.0+).

Endpoint: `api.gdeltproject.org/api/v2/doc/doc?mode=ArtList&format=json`.
No auth; generous rate limits. Gated by v3.6 public-APIs.
"""

from __future__ import annotations

from typing import Any

from . import public_api

ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
DEPTH_LIMITS = {"quick": 25, "default": 75, "deep": 150}


def _format_gdelt_date(iso: str) -> str:
    if not iso:
        return ""
    return iso.replace("-", "") + "000000"  # YYYYMMDDHHMMSS


def search_gdelt(
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
        "query": topic,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": DEPTH_LIMITS.get(depth, 75),
        "sort": "datedesc",
    }
    if from_date:
        params["startdatetime"] = _format_gdelt_date(from_date)
    if to_date:
        params["enddatetime"] = _format_gdelt_date(to_date)
    return public_api.fetch_json(
        ENDPOINT,
        params=params,
        user_agent_suffix="gdelt-adapter",
    )


def parse_gdelt_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    articles = response["items"].get("articles") or []
    out = []
    for a in articles:
        url = a.get("url") or ""
        if not url:
            continue
        seendate = a.get("seendate", "")
        iso_date = f"{seendate[0:4]}-{seendate[4:6]}-{seendate[6:8]}" if len(seendate) >= 8 else ""
        out.append({
            "id": f"gdelt:{url}",
            "title": (a.get("title") or "")[:200],
            "snippet": (a.get("socialimage") and f"Image: {a.get('socialimage')}" or "")[:500],
            "url": url,
            "source_domain": a.get("domain") or "",
            "date": iso_date or None,
            "relevance": 0.65,
            "why_relevant": f"GDELT — {a.get('domain', 'article')}",
            "metadata": {
                "platform": "gdelt",
                "language": a.get("language", ""),
                "sourcecountry": a.get("sourcecountry", ""),
                "seendate": seendate,
            },
        })
    return out
