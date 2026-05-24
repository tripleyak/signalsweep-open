"""Amazon Ads API v2 read-only research adapter (signalsweep 3.7+).

**READ-ONLY.** Like sp_api.py, this module enforces a code-level endpoint
allowlist. Only campaign/keyword/search-term listing endpoints are callable;
any non-allowlisted path raises `NotAllowedEndpoint`. Campaign mutation
operations (create/update campaign, adjust bid, enable/pause) are deliberately
absent.

Auth: Login-with-Amazon (LWA) refresh-token flow via `amazon_auth.py`, shared
with sp_api.py. Access token attached as `Authorization: Bearer <token>`.

Profile + region:
- Ads API requires a profile scope header (`Amazon-Advertising-API-Scope`)
  identifying which advertiser account the request is for.
- Scalar `AMAZON_ADS_PROFILE_ID` — single-profile backward-compat shape.
- `AMAZON_ADS_PROFILES` + `AMAZON_ADS_ACTIVE_PROFILE` — multi-profile dict.
- Region endpoint base is inferred from the active profile's
  `AMAZON_ADS_REGION` key (NA/EU/FE); defaults to NA.

For v3.7.0, `search_ads_api(query)` returns campaigns whose name contains the
query term. Sponsored-products search-term reports are async (create → poll →
download) and land in v3.7.x — out of scope for the initial release.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from . import amazon_auth, amazon_marketplaces, paid_api

DEFAULT_REGION = "NA"

# ALLOWED_ENDPOINTS — the security boundary.
# Sponsored Products campaign/keyword/ad-group LIST endpoints only.
ALLOWED_ENDPOINTS: tuple[str, ...] = (
    "/v2/sp/campaigns",
    "/v2/sp/keywords",
    "/v2/sp/adGroups",
    "/v2/sp/productAds",
    # Search-term reports (async) will land in v3.7.x — allowlist entry gated by
    # future method that enforces GET-only report-download semantics.
)

DEPTH_LIMITS = {
    "quick": 25,
    "default": 100,
    "deep": 500,
}


class NotAllowedEndpoint(Exception):
    """Raised when code attempts to call an endpoint not in `ALLOWED_ENDPOINTS`."""


def _is_allowlisted(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in ALLOWED_ENDPOINTS)


def _resolve_profile(config: dict[str, Any]) -> dict[str, Any]:
    """Overlay active Ads API profile over top-level config. Mirrors sp_api._resolve_profile."""
    active = config.get("AMAZON_ADS_ACTIVE_PROFILE")
    profiles_raw = config.get("AMAZON_ADS_PROFILES")
    if not (active and profiles_raw):
        return config

    try:
        profiles = json.loads(profiles_raw) if isinstance(profiles_raw, str) else profiles_raw
    except (ValueError, TypeError) as err:
        sys.stderr.write(f"[ads_api] WARNING: AMAZON_ADS_PROFILES is not valid JSON: {err}\n")
        return config

    if not isinstance(profiles, dict):
        return config

    profile = profiles.get(active)
    if not isinstance(profile, dict):
        sys.stderr.write(
            f"[ads_api] WARNING: AMAZON_ADS_ACTIVE_PROFILE={active!r} not found; "
            f"available: {list(profiles.keys())}\n"
        )
        return config

    return {**config, **profile}


def _region_base(config: dict[str, Any]) -> str:
    config = _resolve_profile(config)
    region = str(config.get("AMAZON_ADS_REGION") or DEFAULT_REGION).upper()
    endpoints = amazon_marketplaces.ADS_API_ENDPOINTS
    return endpoints.get(region, endpoints[DEFAULT_REGION])


def _profile_id(config: dict[str, Any]) -> str:
    config = _resolve_profile(config)
    return str(config.get("AMAZON_ADS_PROFILE_ID") or "")


def _call_ads_api(
    path: str,
    *,
    params: dict[str, Any] | None,
    config: dict[str, Any],
) -> dict[str, Any]:
    if not _is_allowlisted(path):
        raise NotAllowedEndpoint(
            f"Ads API path not in read-only allowlist: {path}. "
            f"ads_api.py enforces a code-level boundary against mutation operations."
        )

    config = _resolve_profile(config)
    refresh_token = config.get("AMAZON_LWA_REFRESH_TOKEN") or ""
    client_id = config.get("AMAZON_LWA_CLIENT_ID") or ""
    client_secret = config.get("AMAZON_LWA_CLIENT_SECRET") or ""
    profile_id = config.get("AMAZON_ADS_PROFILE_ID") or ""

    if not (refresh_token and client_id and client_secret):
        return {"items": None, "error": "credentials_missing"}
    if not profile_id:
        return {"items": None, "error": "profile_id_missing"}

    access_token, _ = amazon_auth.get_lwa_access_token(refresh_token, client_id, client_secret)
    if not access_token:
        return {"items": None, "error": amazon_auth.get_last_error() or "lwa_token_failed"}

    auth = paid_api.AuthSpec(type="bearer", value=access_token)
    extra_headers = {
        "Amazon-Advertising-API-ClientId": client_id,
        "Amazon-Advertising-API-Scope": str(profile_id),
    }

    url = f"{_region_base(config)}{path}"
    return paid_api.fetch_json(
        url,
        auth=auth,
        params=params,
        extra_headers=extra_headers,
        user_agent_suffix="(ads-api-adapter)",
        cache_key=None,  # advertiser-specific, no cross-run cache
    )


def search_ads_api(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search the active Ads API profile's Sponsored Products campaigns.

    Returns campaigns whose name contains `topic`. For v3.7.0 this is the only
    on-demand synchronous lens. Search-term performance reports (async polling)
    land in v3.7.x.
    """
    config = config or {}
    count = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {
        "count": count,
        "stateFilter": "enabled,paused",  # exclude archived to keep results relevant
    }
    if topic:
        # Ads API v2 campaigns endpoint supports `campaignIdFilter`/`nameFilter` via query.
        params["nameFilter"] = topic
    return _call_ads_api("/v2/sp/campaigns", params=params, config=config)


def parse_ads_api_response(response: dict[str, Any], query: str = "") -> list[dict[str, Any]]:
    """Parse Ads API campaigns response into normalized item dicts."""
    if response.get("error") or not response.get("items"):
        return []

    body = response["items"]
    if not isinstance(body, list):
        return []

    parsed = []
    for i, camp in enumerate(body):
        if not isinstance(camp, dict):
            continue
        campaign_id = camp.get("campaignId")
        name = (camp.get("name") or "").strip()
        if not campaign_id or not name:
            continue

        state = (camp.get("state") or "").strip()
        daily_budget = camp.get("dailyBudget")
        targeting_type = (camp.get("targetingType") or "").strip()
        start_date = camp.get("startDate") or None
        end_date = camp.get("endDate") or None

        snippet_parts = []
        if state:
            snippet_parts.append(f"State: {state}")
        if daily_budget:
            snippet_parts.append(f"Daily budget: ${daily_budget:.2f}" if isinstance(daily_budget, (int, float)) else f"Daily budget: {daily_budget}")
        if targeting_type:
            snippet_parts.append(f"Targeting: {targeting_type}")
        snippet = " · ".join(snippet_parts) or f"Sponsored Products campaign: {name}"

        parsed.append({
            "id": str(campaign_id),
            "title": f"SP campaign: {name}",
            "snippet": snippet,
            "url": f"https://advertising.amazon.com/cm/sp/campaigns/{campaign_id}",
            "source_domain": "advertising.amazon.com",
            "date": start_date,
            "relevance": max(0.3, 1.0 - (i * 0.02)),
            "why_relevant": f"Ads API campaign match for '{query}'" if query else "Ads API campaign match",
            "metadata": {
                "campaign_id": campaign_id,
                "name": name,
                "state": state,
                "daily_budget": daily_budget,
                "targeting_type": targeting_type,
                "start_date": start_date,
                "end_date": end_date,
            },
        })
    return parsed
