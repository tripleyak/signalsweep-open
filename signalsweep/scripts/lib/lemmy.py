"""Lemmy federated link aggregator (signalsweep 3.23.0+).

Endpoint: `{instance}/api/v3/search?q=X&type_=All`. Public, no auth.
Default instance `lemmy.world` (currently the largest public instance).

Config: `LEMMY_INSTANCE_URL` (default `https://lemmy.world`).
v3.6 public-APIs tier.
"""

from __future__ import annotations

from typing import Any

from . import public_api

DEFAULT_INSTANCE = "https://lemmy.world"
DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 40}


def search_lemmy(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not public_api.is_public_apis_enabled(cfg):
        return {"items": None, "error": "public_apis_disabled"}
    instance = (cfg.get("LEMMY_INSTANCE_URL") or DEFAULT_INSTANCE).rstrip("/")
    url = f"{instance}/api/v3/search"
    params = {"q": topic, "type_": "All", "limit": DEPTH_LIMITS.get(depth, 25), "sort": "TopMonth"}
    return public_api.fetch_json(
        url,
        params=params,
        user_agent_suffix="lemmy-adapter",
    )


def parse_lemmy_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    posts = response["items"].get("posts") or []
    out = []
    for p in posts:
        post = p.get("post") or {}
        pid = post.get("id")
        if not pid:
            continue
        creator = p.get("creator") or {}
        counts = p.get("counts") or {}
        out.append({
            "id": f"lemmy:{pid}",
            "title": (post.get("name") or "")[:200],
            "snippet": (post.get("body") or post.get("url") or "")[:500],
            "url": post.get("ap_id") or post.get("url") or "",
            "source_domain": "lemmy.world",
            "date": (post.get("published") or "")[:10],
            "author": creator.get("name"),
            "relevance": 0.65,
            "why_relevant": f"Lemmy post by {creator.get('name', '?')}",
            "metadata": {
                "platform": "lemmy",
                "post_id": pid,
                "community": (p.get("community") or {}).get("name"),
                "score": counts.get("score", 0),
                "comments": counts.get("comments", 0),
                "upvotes": counts.get("upvotes", 0),
            },
        })
    return out
