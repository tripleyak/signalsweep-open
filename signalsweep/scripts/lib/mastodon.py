"""Mastodon instance search (signalsweep 3.23.0+).

Endpoint: `{instance}/api/v2/search?q=X&type=statuses`. Public without auth
for many instances. Default instance `mastodon.social`.

Config: `MASTODON_INSTANCE_URL` (default `https://mastodon.social`),
`MASTODON_ACCESS_TOKEN` (optional — unlocks full-text search on instances
that require auth).

v3.6 public-APIs tier.
"""

from __future__ import annotations

from typing import Any

from . import public_api

DEFAULT_INSTANCE = "https://mastodon.social"
DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 40}


def search_mastodon(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not public_api.is_public_apis_enabled(cfg):
        return {"items": None, "error": "public_apis_disabled"}
    instance = (cfg.get("MASTODON_INSTANCE_URL") or DEFAULT_INSTANCE).rstrip("/")
    token = cfg.get("MASTODON_ACCESS_TOKEN")
    url = f"{instance}/api/v2/search"
    params = {"q": topic, "type": "statuses", "limit": DEPTH_LIMITS.get(depth, 25)}
    extra_headers = {"Authorization": f"Bearer {token}"} if token else None
    return public_api.fetch_json(
        url,
        params=params,
        extra_headers=extra_headers,
        user_agent_suffix="mastodon-adapter",
    )


def parse_mastodon_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    statuses = response["items"].get("statuses") or []
    out = []
    for s in statuses:
        sid = s.get("id")
        if not sid:
            continue
        account = s.get("account") or {}
        # Strip HTML from content for snippet
        content_html = s.get("content", "")
        import re
        content_text = re.sub(r"<[^>]+>", "", content_html)
        out.append({
            "id": f"mastodon:{sid}",
            "title": f"@{account.get('acct', '?')} — {content_text[:80]}",
            "snippet": content_text[:500],
            "url": s.get("url") or s.get("uri") or "",
            "source_domain": "mastodon.social",
            "date": (s.get("created_at") or "")[:10],
            "author": account.get("acct"),
            "relevance": 0.65,
            "why_relevant": f"Mastodon status by @{account.get('acct', '?')}",
            "metadata": {
                "platform": "mastodon",
                "status_id": sid,
                "reblogs_count": s.get("reblogs_count", 0),
                "favourites_count": s.get("favourites_count", 0),
                "replies_count": s.get("replies_count", 0),
                "language": s.get("language"),
                "visibility": s.get("visibility"),
            },
        })
    return out
