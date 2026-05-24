"""Podchaser podcast search — GraphQL, envelope-first (signalsweep 3.25.0+).

Endpoint: `api.podchaser.com/graphql`. Requires `PODCHASER_CLIENT_ID` +
`PODCHASER_CLIENT_SECRET` (or pre-fetched `PODCHASER_ACCESS_TOKEN`).

This adapter implements the access-token path; client_credentials flow
deferred (use `marketplace_oauth.py` in a future release if needed).

v3.7 paid-APIs + creds.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

ENDPOINT = "https://api.podchaser.com/graphql"

QUERY = """
query PodcastSearch($searchTerm: String!) {
  podcasts(searchTerm: $searchTerm, first: 25) {
    data { id title description webUrl ratingAverage ratingCount }
  }
}
"""


def search_podchaser(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    token = cfg.get("PODCHASER_ACCESS_TOKEN")
    if not token:
        return {"items": None, "error": "credentials_missing"}
    return paid_api.post_json(
        ENDPOINT,
        json_body={"query": QUERY, "variables": {"searchTerm": topic}},
        extra_headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )


def parse_podchaser_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    data = response["items"].get("data") or {}
    podcasts = (data.get("podcasts") or {}).get("data") or []
    out = []
    for p in podcasts:
        pid = p.get("id")
        if not pid:
            continue
        out.append({
            "id": f"podchaser:{pid}",
            "title": (p.get("title") or "")[:200],
            "snippet": (p.get("description") or "")[:500],
            "url": p.get("webUrl") or "",
            "source_domain": "podchaser.com",
            "date": None,
            "relevance": 0.7,
            "why_relevant": f"Podchaser podcast — {p.get('title', '')[:60]}",
            "metadata": {
                "platform": "podchaser",
                "podcast_id": pid,
                "rating_average": p.get("ratingAverage"),
                "rating_count": p.get("ratingCount"),
            },
        })
    return out
