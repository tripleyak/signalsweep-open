"""UK Office for National Statistics search (signalsweep 3.6.1+).

No auth required. Searches the ONS Beta API for datasets matching the topic.
Returns dataset metadata items.

Endpoint: https://api.beta.ons.gov.uk/v1/search?content_type=dataset&q=<query>
"""

from __future__ import annotations

from typing import Any

from . import public_api


SEARCH_URL = "https://api.beta.ons.gov.uk/v1/search"

DEPTH_LIMITS = {
    "quick": 10,
    "default": 25,
    "deep": 50,
}


def search_uk_ons(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch a page of ONS dataset search results."""
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {
        "content_type": "dataset",
        "q": topic,
        "limit": limit,
    }
    return public_api.fetch_json(
        SEARCH_URL,
        params=params,
        cache_key=f"uk_ons:{topic}:{depth}",
        user_agent_suffix="(uk_ons-adapter)",
    )


def parse_uk_ons_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    payload = response["items"]
    if not isinstance(payload, dict):
        return []

    items = payload.get("items") or []
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for ds in items:
        if not isinstance(ds, dict):
            continue
        title = (ds.get("title") or "").strip()
        description = (ds.get("description") or ds.get("summary") or "").strip()
        uri = ds.get("uri") or ds.get("url") or ""
        release_date = ds.get("release_date") or ds.get("updated") or ""
        ds_id = ds.get("id") or ds.get("cdid") or uri or title

        if not title:
            continue

        # ONS URIs are relative paths like "/datasets/cpih01"; absolutize.
        if uri.startswith("/"):
            url = f"https://www.ons.gov.uk{uri}"
        elif uri:
            url = uri
        else:
            url = "https://www.ons.gov.uk"

        parsed.append({
            "id": str(ds_id),
            "title": title,
            "snippet": description[:500],
            "url": url,
            "date": (release_date or "")[:10] if release_date else None,
            "source_domain": "ons.gov.uk",
            "relevance": 0.6,
            "why_relevant": f"UK ONS dataset: {title[:60]}",
            "metadata": {
                "release_date": release_date,
                "type": ds.get("type") or "dataset",
            },
        })
        if len(parsed) >= limit:
            break
    return parsed
