"""Pinterest API v5 commerce (signalsweep 3.14.0+).

Pinterest's v5 API surfaces pins + catalogs. For research purposes, the
"search pins" endpoint (v5 pins search) surfaces what Pinterest users are
actively engaging with — a commerce-adjacent signal complementary to
v3.9.0's `pinterest_trends` (advertiser-aggregated trending searches).

Auth: OAuth 2.0 Bearer (authorization-code flow). Requires:
  `PINTEREST_CLIENT_ID`
  `PINTEREST_CLIENT_SECRET`
  `PINTEREST_OAUTH_REFRESH_TOKEN`

Envelope-first: any missing credential → `credentials_missing`.

Docs: developers.pinterest.com/docs/api/v5
"""

from __future__ import annotations

from typing import Any

from . import marketplace_oauth


TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"
SEARCH_URL = "https://api.pinterest.com/v5/pins/search"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_pinterest_commerce(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    client_id = config.get("PINTEREST_CLIENT_ID") or ""
    client_secret = config.get("PINTEREST_CLIENT_SECRET") or ""
    refresh_token = config.get("PINTEREST_OAUTH_REFRESH_TOKEN") or ""

    if not (client_id and client_secret and refresh_token):
        return {"items": None, "error": "credentials_missing"}

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {"query": topic, "page_size": limit}

    return marketplace_oauth.fetch_with_bearer(
        SEARCH_URL,
        vendor="pinterest_commerce",
        token_url=TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret,
        grant_type="refresh_token",
        refresh_token=refresh_token,
        params=params,
        cache_key=f"pinterest_commerce:{topic}:{depth}",
        user_agent_suffix="(pinterest_commerce-adapter)",
    )


def parse_pinterest_commerce_response(
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

    pins = payload.get("items") or payload.get("data") or []
    if not isinstance(pins, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for pin in pins[:limit]:
        if not isinstance(pin, dict):
            continue
        pin_id = pin.get("id") or ""
        title = (pin.get("title") or pin.get("description") or "").strip()
        if not pin_id or not title:
            continue

        description = (pin.get("description") or "")[:500]
        link = pin.get("link") or f"https://www.pinterest.com/pin/{pin_id}/"
        board_id = pin.get("board_id") or ""

        try:
            saves = int((pin.get("pin_metrics") or {}).get("lifetime_saves", 0) or 0)
        except (TypeError, ValueError):
            saves = 0
        try:
            impressions = int((pin.get("pin_metrics") or {}).get("lifetime_impressions", 0) or 0)
        except (TypeError, ValueError):
            impressions = 0

        parsed.append({
            "id": f"pinterest_pin:{pin_id}",
            "title": title[:200],
            "snippet": description or f"Pinterest pin — {saves:,} saves, {impressions:,} impressions",
            "url": link,
            "source_domain": "pinterest.com",
            "date": pin.get("created_at", "")[:10] or to_date or None,
            "relevance": 0.65,
            "why_relevant": f"Pinterest commerce match for '{query[:40]}'" if query else title[:60],
            "engagement_score": float(saves * 5 + impressions),
            "metadata": {
                "pin_id": pin_id,
                "board_id": board_id,
                "saves": saves,
                "impressions": impressions,
            },
        })
    return parsed
