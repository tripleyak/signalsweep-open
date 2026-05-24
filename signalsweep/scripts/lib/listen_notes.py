"""Listen Notes podcast search (signalsweep 3.25.0+).

Endpoint: `listen-api.listennotes.com/api/v2/search`. Requires
`LISTENNOTES_API_KEY`. Free dev tier available.

v3.7 paid-APIs + creds.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

ENDPOINT = "https://listen-api.listennotes.com/api/v2/search"


def search_listen_notes(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = cfg.get("LISTENNOTES_API_KEY") or cfg.get("LISTEN_NOTES_API_KEY")
    if not api_key:
        return {"items": None, "error": "credentials_missing"}
    params = {"q": topic, "type": "episode", "sort_by_date": 0, "safe_mode": 0}
    return paid_api.fetch_json(ENDPOINT, params=params, extra_headers={"X-ListenAPI-Key": api_key})


def parse_listen_notes_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    results = response["items"].get("results") or []
    out = []
    for r in results:
        rid = r.get("id")
        if not rid:
            continue
        podcast = r.get("podcast") or {}
        out.append({
            "id": f"listen_notes:{rid}",
            "title": (r.get("title_original") or "")[:200],
            "snippet": (r.get("description_original") or "")[:500],
            "url": r.get("link") or r.get("listennotes_url") or "",
            "source_domain": "listennotes.com",
            "date": None,
            "relevance": 0.7,
            "why_relevant": f"Listen Notes episode — {podcast.get('title_original', 'podcast')[:40]}",
            "metadata": {
                "platform": "listen_notes",
                "episode_id": rid,
                "podcast_title": podcast.get("title_original"),
                "podcast_id": podcast.get("id"),
                "audio_length_sec": r.get("audio_length_sec"),
                "pub_date_ms": r.get("pub_date_ms"),
            },
        })
    return out
