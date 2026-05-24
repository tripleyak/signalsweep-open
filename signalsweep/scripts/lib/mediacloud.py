"""MediaCloud — news media analysis platform (signalsweep 3.20.0+).

Endpoint: `api.mediacloud.org/api/v2/stories_public/list`. Requires
`MEDIACLOUD_API_KEY`. Gated by v3.7 paid-APIs + creds.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

ENDPOINT = "https://api.mediacloud.org/api/v2/stories_public/list"
DEPTH_LIMITS = {"quick": 25, "default": 75, "deep": 200}


def search_mediacloud(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = cfg.get("MEDIACLOUD_API_KEY")
    if not api_key:
        return {"items": None, "error": "credentials_missing"}
    q_parts = [topic]
    if from_date and to_date:
        q_parts.append(f"publish_date:[{from_date}T00:00:00Z TO {to_date}T23:59:59Z]")
    params = {
        "key": api_key,
        "q": " AND ".join(q_parts),
        "rows": DEPTH_LIMITS.get(depth, 75),
    }
    return paid_api.fetch_json(ENDPOINT, params=params)


def parse_mediacloud_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    stories = response["items"] if isinstance(response["items"], list) else response["items"].get("results") or []
    out = []
    for s in stories:
        url = s.get("url") or ""
        if not url:
            continue
        stories_id = s.get("stories_id") or s.get("id") or url
        out.append({
            "id": f"mediacloud:{stories_id}",
            "title": (s.get("title") or "")[:200],
            "snippet": (s.get("description") or "")[:500],
            "url": url,
            "source_domain": s.get("media_name") or s.get("publish_domain") or "mediacloud.org",
            "date": (s.get("publish_date") or "")[:10],
            "relevance": 0.68,
            "why_relevant": f"MediaCloud — {s.get('media_name', 'article')}",
            "metadata": {
                "platform": "mediacloud",
                "stories_id": stories_id,
                "media_id": s.get("media_id"),
                "media_name": s.get("media_name"),
                "language": s.get("language"),
            },
        })
    return out
