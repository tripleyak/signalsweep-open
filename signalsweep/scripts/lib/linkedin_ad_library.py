"""LinkedIn Ad Library — envelope-first via Marketing API (signalsweep 3.16.3+).

LinkedIn's Ad Library (launched 2024, post-EU DSA) surfaces every LinkedIn
ad with targeting hints. **Envelope-first** — scraping is intentionally
deferred pending TOS clarity. LinkedIn's User Agreement §8.2 prohibits
automated scraping; signalsweep CLAUDE.md prohibits this class of work.

The adapter calls LinkedIn's Marketing API programmatic Ad Library endpoint.
Access is gated behind LinkedIn advertiser approval; users with active
Campaign Manager accounts can generate an OAuth refresh-token and unlock
this adapter. Others see `credentials_missing` envelope.

**Auth:** OAuth 2.0 refresh-token flow via `marketplace_oauth.py` (same
helper used for Pinterest Commerce + TikTok Shop Partner in v3.14).

Env:
  `LINKEDIN_MARKETING_CLIENT_ID`
  `LINKEDIN_MARKETING_CLIENT_SECRET`
  `LINKEDIN_MARKETING_REFRESH_TOKEN`
  `LINKEDIN_AD_LIBRARY_COUNTRIES` (optional, default `US`)
  `LINKEDIN_AD_LIBRARY_SEARCH_MODE` (optional, `terms` | `company_id`)
  `LINKEDIN_MARKETING_API_VERSION` (optional, default `202404`)

**Scope:** companion to v3.5 `linkedin` (post-level ScrapeCreators-backed).
This adapter is strictly for paid-campaign creative research.

Docs: learn.microsoft.com/en-us/linkedin/marketing/
"""

from __future__ import annotations

import sys
from typing import Any

from . import marketplace_oauth, paid_api


TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
DEFAULT_API_VERSION = "202404"
SEARCH_URL_TEMPLATE = "https://api.linkedin.com/rest/adLibrary"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def _build_search_url(api_version: str) -> str:
    return SEARCH_URL_TEMPLATE


def search_linkedin_ad_library(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}

    client_id = config.get("LINKEDIN_MARKETING_CLIENT_ID") or ""
    client_secret = config.get("LINKEDIN_MARKETING_CLIENT_SECRET") or ""
    refresh_token = config.get("LINKEDIN_MARKETING_REFRESH_TOKEN") or ""

    if not (client_id and client_secret and refresh_token):
        return {"items": None, "error": "credentials_missing"}

    countries_raw = config.get("LINKEDIN_AD_LIBRARY_COUNTRIES") or "US"
    countries = [c.strip().upper() for c in str(countries_raw).split(",") if c.strip()]
    if not countries:
        countries = ["US"]

    search_mode = (config.get("LINKEDIN_AD_LIBRARY_SEARCH_MODE") or "terms").strip().lower()
    api_version = (config.get("LINKEDIN_MARKETING_API_VERSION") or DEFAULT_API_VERSION).strip()

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    params: dict[str, Any] = {
        "countries": ",".join(countries),
        "count": limit,
    }
    if search_mode == "company_id":
        # LinkedIn URN format for company pages
        company_id = topic.strip()
        if not company_id.startswith("urn:li:organization:"):
            company_id = f"urn:li:organization:{company_id}"
        params["advertiser"] = company_id
    else:
        params["keywords"] = topic

    result = marketplace_oauth.fetch_with_bearer(
        _build_search_url(api_version),
        vendor="linkedin",
        token_url=TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret,
        grant_type="refresh_token",
        refresh_token=refresh_token,
        params=params,
        extra_headers={
            "LinkedIn-Version": api_version,
            "X-Restli-Protocol-Version": "2.0.0",
        },
        user_agent_suffix="(linkedin_ad_library-adapter)",
    )
    return result


def parse_linkedin_ad_library_response(
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

    ads = payload.get("elements") or payload.get("ads") or payload.get("data") or []
    if not isinstance(ads, list):
        sys.stderr.write(
            "[linkedin_ad_library] schema drift: ads field not a list; returning []\n"
        )
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for ad in ads[:limit]:
        if not isinstance(ad, dict):
            continue
        ad_id = ad.get("id") or ad.get("adId") or ""
        advertiser_urn = ad.get("advertiser") or ad.get("sponsor") or ""
        advertiser_name = (ad.get("advertiserName") or ad.get("sponsorName") or ad.get("companyName") or "").strip()
        if not ad_id or not advertiser_name:
            continue

        # Extract numeric company ID from URN (e.g., urn:li:organization:12345)
        company_id = ""
        if isinstance(advertiser_urn, str) and ":" in advertiser_urn:
            company_id = advertiser_urn.split(":")[-1]

        creative_text = (ad.get("commentary") or ad.get("adText") or ad.get("creativeText") or "").strip()
        title_text = (creative_text[:200] if creative_text else f"{advertiser_name} — ad {ad_id[:12]}")

        delivery_start = ad.get("firstImpressionAt") or ad.get("startDate") or ""
        delivery_stop = ad.get("lastImpressionAt") or ad.get("endDate") or ""

        countries_raw = ad.get("targetedCountries") or ad.get("countries") or []
        countries: list[str] = [str(c) for c in countries_raw] if isinstance(countries_raw, list) else []

        # Spend range (EU DSA — may be present)
        spend_obj = ad.get("spend") or {}
        spend_range = ""
        if isinstance(spend_obj, dict) and spend_obj.get("lowerBound") is not None:
            lo = spend_obj.get("lowerBound")
            hi = spend_obj.get("upperBound", "?")
            currency = spend_obj.get("currencyCode", "USD")
            spend_range = f"{currency} {lo}-{hi}"

        impressions_obj = ad.get("impressions") or {}
        impr_range = ""
        if isinstance(impressions_obj, dict) and impressions_obj.get("lowerBound") is not None:
            lo = impressions_obj.get("lowerBound")
            hi = impressions_obj.get("upperBound", "?")
            impr_range = f"{lo}-{hi}"

        snippet_parts = []
        if creative_text:
            snippet_parts.append(creative_text[:300])
        if countries:
            snippet_parts.append(f"Countries: {', '.join(countries[:5])}")
        if delivery_start:
            snippet_parts.append(f"Started: {delivery_start[:10]}")
        if spend_range:
            snippet_parts.append(f"Spend: {spend_range}")
        if impr_range:
            snippet_parts.append(f"Impressions: {impr_range}")
        snippet = " · ".join(snippet_parts)[:500] or f"LinkedIn ad by {advertiser_name}"

        parsed.append({
            "id": f"linkedin_ad:{ad_id}",
            "title": title_text,
            "snippet": snippet,
            "url": f"https://www.linkedin.com/ad-library/detail/{ad_id}",
            "source_domain": "linkedin.com",
            "date": (delivery_start[:10] if delivery_start else None),
            "author": advertiser_name,
            "relevance": 0.7,
            "why_relevant": f"LinkedIn ad by {advertiser_name}" + (
                f" (matching '{query[:40]}')" if query else ""
            ),
            "metadata": {
                "ad_id": ad_id,
                "advertiser_urn": advertiser_urn,
                "company_id": company_id,
                "advertiser_name": advertiser_name,
                "countries": countries,
                "delivery_start": delivery_start,
                "delivery_stop": delivery_stop,
                "spend_range": spend_range,
                "impressions_range": impr_range,
            },
        })
    return parsed
