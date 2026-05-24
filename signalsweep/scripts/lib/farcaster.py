"""Farcaster casts via Neynar API (signalsweep 3.23.0+).

Endpoint: `api.neynar.com/v2/farcaster/cast/search?q=X`.
Requires `NEYNAR_API_KEY` (Farcaster Hub API via Neynar).

v3.7 paid-APIs + creds.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

ENDPOINT = "https://api.neynar.com/v2/farcaster/cast/search"
DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_farcaster(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = cfg.get("NEYNAR_API_KEY")
    if not api_key:
        return {"items": None, "error": "credentials_missing"}
    params = {"q": topic, "limit": DEPTH_LIMITS.get(depth, 25)}
    return paid_api.fetch_json(
        ENDPOINT,
        params=params,
        extra_headers={"api_key": api_key, "accept": "application/json"},
    )


def parse_farcaster_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    result = response["items"].get("result") or {}
    casts = result.get("casts") or []
    out = []
    for c in casts:
        chash = c.get("hash")
        if not chash:
            continue
        author = c.get("author") or {}
        reactions = c.get("reactions") or {}
        out.append({
            "id": f"farcaster:{chash}",
            "title": f"@{author.get('username', '?')} — {(c.get('text') or '')[:80]}",
            "snippet": (c.get("text") or "")[:500],
            "url": f"https://warpcast.com/{author.get('username', '')}/{chash[:10]}",
            "source_domain": "farcaster.xyz",
            "date": (c.get("timestamp") or "")[:10],
            "author": author.get("username"),
            "relevance": 0.65,
            "why_relevant": f"Farcaster cast by @{author.get('username', '?')}",
            "metadata": {
                "platform": "farcaster",
                "cast_hash": chash,
                "author_fid": author.get("fid"),
                "likes_count": reactions.get("likes_count", 0),
                "recasts_count": reactions.get("recasts_count", 0),
                "channel": (c.get("channel") or {}).get("id"),
            },
        })
    return out
