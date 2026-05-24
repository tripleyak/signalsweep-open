"""Wikipedia Recent Changes via MediaWiki API (signalsweep 3.6+).

No auth. Returns recent edits filtered by topic match.
"""

from __future__ import annotations

from typing import Any

from . import public_api


API_URL = "https://en.wikipedia.org/w/api.php"

DEPTH_LIMITS = {
    "quick": 25,
    "default": 100,
    "deep": 250,
}


def search_wiki_recent_changes(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {
        "action": "query",
        "list": "recentchanges",
        "rcnamespace": 0,  # main namespace (articles)
        "rclimit": limit,
        "rcdir": "older",
        "rcstart": f"{to_date}T23:59:59Z",
        "rcend": f"{from_date}T00:00:00Z",
        "rcprop": "title|timestamp|user|comment|sizes",
        "rcshow": "!minor",
        "format": "json",
    }
    return public_api.fetch_json(
        API_URL,
        params=params,
        cache_key=f"wiki-rc:{topic}:{from_date}:{to_date}:{depth}",
        user_agent_suffix="(wiki-recent-changes-adapter)",
    )


def _matches(change: dict[str, Any], tokens: set[str]) -> bool:
    if not tokens:
        return True
    hay = f"{change.get('title', '')} {change.get('comment', '')}".lower()
    return any(tok in hay for tok in tokens)


def parse_wiki_recent_changes_response(
    response: dict[str, Any],
    query: str = "",
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    changes = (response["items"].get("query") or {}).get("recentchanges") or []
    tokens = {t.strip().lower() for t in query.split() if len(t.strip()) >= 3}

    parsed = []
    for c in changes:
        title = (c.get("title") or "").strip()
        if not _matches(c, tokens):
            continue

        ts = c.get("timestamp") or ""
        date = ts[:10] if ts else None
        user = (c.get("user") or "").strip()
        comment = (c.get("comment") or "").strip()
        old_len = c.get("oldlen") or 0
        new_len = c.get("newlen") or 0
        delta = new_len - old_len

        url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
        parsed.append({
            "id": f"rc:{c.get('rcid') or title}:{ts}",
            "title": f"Edit to {title}" + (f" — {comment[:60]}" if comment else ""),
            "snippet": f"Edit by {user} ({delta:+d} bytes): {comment[:200]}",
            "url": url,
            "date": date,
            "source_domain": "en.wikipedia.org",
            "relevance": 0.5,
            "why_relevant": f"Wikipedia edit on '{title}'",
            "metadata": {
                "article_title": title,
                "editor": user,
                "size_delta": delta,
                "comment": comment,
            },
        })
    return parsed
