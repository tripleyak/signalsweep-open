"""Walmart Connect (Advertising) API — read-only campaign research (signalsweep 3.14.0+).

**READ-ONLY.** Campaign + ad-group listings only. Budget updates, creative
edits, bid changes are deliberately absent.

Auth: OAuth 2.0 client-credentials flow via `marketplace_oauth.py`. Requires:
  `WALMART_CONNECT_CLIENT_ID`
  `WALMART_CONNECT_CLIENT_SECRET`

Approved-advertiser-only. Ships with `credentials_missing` envelope.

Docs: developer.walmart.com/doc/us/advertising/
"""

from __future__ import annotations

from typing import Any

from . import marketplace_oauth


TOKEN_URL = "https://advertising-api.walmart.com/v1/auth/token"
BASE_URL = "https://advertising-api.walmart.com"

ALLOWED_ENDPOINTS: tuple[str, ...] = (
    "/v1/campaign",          # campaign listing (GET)
    "/v1/adGroups",          # ad-group listing (GET)
    "/v1/reports",           # reports download
    "/v1/keyword",           # keyword listing (GET)
)

DEPTH_LIMITS = {"quick": 5, "default": 10, "deep": 25}


class NotAllowedEndpoint(Exception):
    pass


def _is_allowlisted(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in ALLOWED_ENDPOINTS)


def search_walmart_connect(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    client_id = config.get("WALMART_CONNECT_CLIENT_ID") or ""
    client_secret = config.get("WALMART_CONNECT_CLIENT_SECRET") or ""
    if not (client_id and client_secret):
        return {"items": None, "error": "credentials_missing"}

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    path = "/v1/campaign"

    if not _is_allowlisted(path):
        raise NotAllowedEndpoint(f"Walmart Connect path not in read-only allowlist: {path}")

    params = {"query": topic, "limit": limit}

    return marketplace_oauth.fetch_with_bearer(
        f"{BASE_URL}{path}",
        vendor="walmart_connect",
        token_url=TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret,
        grant_type="client_credentials",
        params=params,
        cache_key=None,
        user_agent_suffix="(walmart-connect-adapter)",
    )


def parse_walmart_connect_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    body = response["items"]
    if not isinstance(body, dict):
        return []

    campaigns = body.get("campaigns") or body.get("response") or body.get("data") or []
    if not isinstance(campaigns, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for i, campaign in enumerate(campaigns[:limit]):
        if not isinstance(campaign, dict):
            continue
        campaign_id = campaign.get("campaignId") or campaign.get("id") or ""
        name = (campaign.get("name") or campaign.get("campaignName") or "").strip()
        if not campaign_id or not name:
            continue

        status = (campaign.get("status") or campaign.get("state") or "").strip()
        budget = 0.0
        try:
            budget = float(campaign.get("dailyBudget") or campaign.get("totalBudget") or 0)
        except (TypeError, ValueError):
            budget = 0.0

        parsed.append({
            "id": f"walmart_connect:{campaign_id}",
            "title": name[:200],
            "snippet": f"Walmart Connect campaign — status: {status}, budget: ${budget:.2f}",
            "url": f"https://advertising.walmart.com/cm/campaigns/{campaign_id}",
            "source_domain": "advertising.walmart.com",
            "date": to_date or None,
            "relevance": max(0.3, 0.7 - (i * 0.02)),
            "why_relevant": f"Walmart Connect campaign match for '{query[:40]}'" if query else name[:60],
            "metadata": {
                "campaign_id": campaign_id,
                "status": status,
                "budget": budget,
            },
        })
    return parsed
