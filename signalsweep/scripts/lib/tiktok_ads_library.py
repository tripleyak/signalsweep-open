"""TikTok Ads Library — advertiser-posted ads (signalsweep 3.16.2+).

TikTok's EU-DSA-mandated Commercial Content Library at `library.tiktok.com/ads`
surfaces ads submitted by advertisers for research access. Coverage is
EU-weighted but includes many global advertisers who also serve EU.

**Companion adapters:**
- `tiktok_creative_center` (v3.9) — trending hashtags for organic content
- `tiktok_shop` (v3.7) — consumer-side Shop catalog via ScrapeCreators
- `tiktok_shop_seller` (v3.14) — authenticated seller dashboard via Partner API
- `tiktok_ads_library` (this module) — advertiser paid-ad creative intelligence

**Auth:** none. Public DSA-compliance endpoint. 500ms polite-sleep per call;
graceful-degrade parser.

**Gating:** v3.7 `SIGNALSWEEP_DISABLE_PAID_APIS` (ad-library tier consistency).

Docs: EU DSA Article 39 (VLOP public-ad-repository); library.tiktok.com/ads
DevTools inspection required at implementation time for endpoint verification.
"""

from __future__ import annotations

import sys
import time
from typing import Any

from . import paid_api


DEFAULT_ENDPOINT = "https://library.tiktok.com/api/v1/search"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}

POLITE_SLEEP_MS = 500


def search_tiktok_ads_library(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}

    countries_raw = config.get("TIKTOK_ADS_LIBRARY_COUNTRIES") or "US"
    countries = [c.strip().upper() for c in str(countries_raw).split(",") if c.strip()]
    if not countries:
        countries = ["US"]

    search_mode = (config.get("TIKTOK_ADS_LIBRARY_SEARCH_MODE") or "terms").strip().lower()
    endpoint = config.get("TIKTOK_ADS_LIBRARY_ENDPOINT") or DEFAULT_ENDPOINT
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    body: dict[str, Any] = {
        "regionCodes": countries,
        "searchMode": search_mode,
        "limit": limit,
    }
    if search_mode == "advertiser_id":
        body["advertiserIds"] = [topic]
    else:
        body["searchQuery"] = topic

    result = paid_api.post_json(
        endpoint,
        data=body,
        user_agent_suffix="(tiktok_ads_library-adapter)",
    )

    time.sleep(POLITE_SLEEP_MS / 1000.0)
    return result


def parse_tiktok_ads_library_response(
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

    ads = payload.get("ads") or payload.get("results") or payload.get("data") or []
    if not isinstance(ads, list):
        sys.stderr.write(
            "[tiktok_ads_library] schema drift: ads field not a list; returning []\n"
        )
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for ad in ads[:limit]:
        if not isinstance(ad, dict):
            continue
        ad_id = ad.get("adId") or ad.get("id") or ""
        advertiser_id = ad.get("advertiserId") or ""
        advertiser_name = (ad.get("advertiserName") or ad.get("advertiserDisplayName") or "").strip()
        if not ad_id or not advertiser_name:
            continue

        creative_text = (ad.get("creativeText") or ad.get("adText") or ad.get("description") or "").strip()
        title_text = (creative_text[:200] if creative_text else f"{advertiser_name} — ad {ad_id[:12]}")

        ad_format = (ad.get("format") or ad.get("creativeFormat") or "").strip()
        thumbnail_url = ad.get("thumbnailUrl") or ad.get("preview_image") or ""
        landing_page = ad.get("landingPage") or ad.get("destinationUrl") or ""
        first_shown = ad.get("firstShown") or ad.get("startDate") or ""
        last_shown = ad.get("lastShown") or ad.get("endDate") or ""
        countries_raw = ad.get("countries") or ad.get("regionCodes") or []
        countries: list[str] = [str(c) for c in countries_raw] if isinstance(countries_raw, list) else []

        snippet_parts = []
        if creative_text:
            snippet_parts.append(creative_text[:300])
        if countries:
            snippet_parts.append(f"Countries: {', '.join(countries[:5])}")
        if first_shown:
            snippet_parts.append(f"First shown: {first_shown[:10]}")
        if ad_format:
            snippet_parts.append(f"Format: {ad_format}")
        snippet = " · ".join(snippet_parts)[:500] or f"TikTok ad by {advertiser_name}"

        parsed.append({
            "id": f"tiktok_ads:{ad_id}",
            "title": title_text,
            "snippet": snippet,
            "url": f"https://library.tiktok.com/ads/detail/{ad_id}",
            "source_domain": "library.tiktok.com",
            "date": (first_shown[:10] if first_shown else None),
            "author": advertiser_name,
            "relevance": 0.7,
            "why_relevant": f"TikTok ad by {advertiser_name}" + (
                f" (matching '{query[:40]}')" if query else ""
            ),
            "metadata": {
                "ad_id": ad_id,
                "advertiser_id": advertiser_id,
                "advertiser_name": advertiser_name,
                "format": ad_format,
                "countries": countries,
                "first_shown": first_shown,
                "last_shown": last_shown,
                "landing_page": landing_page,
                "thumbnail_url": thumbnail_url,
            },
        })
    return parsed
