"""Google Ads Transparency Center — every Google ad a verified advertiser is running (signalsweep 3.16.1+).

Google launched the Ads Transparency Center in 2023 as a public, searchable
archive of every ad any verified advertiser is currently (or recently) running.
Completes the paid-search competitive picture alongside v3.16.0's Meta Ad Library.

**Auth:** none. Public backend endpoint behind adstransparency.google.com.
No API key, no OAuth. Reverse-engineered endpoint shape — may drift.

**Scope:** text + image + video ads from verified advertisers, with
advertiser identity, first/last shown dates, region list, landing page,
and creative text.

**TOS posture:** 500ms polite-sleep per call; graceful-degrade parser
(returns `[]` on unexpected shape rather than raising). Gated by v3.7
`SIGNALSWEEP_DISABLE_PAID_APIS` toggle for consistent ad-library tier
operator experience.

Docs: transparency.google.com/help/ads + DevTools Network inspection of
adstransparency.google.com for endpoint + request body verification.
"""

from __future__ import annotations

import sys
import time
from typing import Any

from . import paid_api


DEFAULT_ENDPOINT = "https://adstransparency.google.com/anji/_/rpc/SearchService/SearchCreatives"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}

POLITE_SLEEP_MS = 500


def search_google_ads_transparency(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}

    countries_raw = config.get("GOOGLE_ADS_TRANSPARENCY_COUNTRIES") or "US"
    countries = [c.strip().upper() for c in str(countries_raw).split(",") if c.strip()]
    if not countries:
        countries = ["US"]

    search_mode = (config.get("GOOGLE_ADS_TRANSPARENCY_SEARCH_MODE") or "terms").strip().lower()
    date_range = (config.get("GOOGLE_ADS_TRANSPARENCY_DATE_RANGE") or "30").strip()
    endpoint = config.get("GOOGLE_ADS_TRANSPARENCY_ENDPOINT") or DEFAULT_ENDPOINT
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    # Request body shape is reverse-engineered from DevTools inspection.
    # Actual endpoint accepts a batch-RPC POST with a JSON payload. Parser
    # tolerates response drift; if the backend changes shape, adapter returns
    # empty rather than raising.
    body: dict[str, Any] = {
        "regionCodes": countries,
        "searchMode": search_mode,
        "dateRange": date_range,
        "limit": limit,
    }
    if search_mode == "advertiser_id":
        body["advertiserIds"] = [topic]
    else:
        body["searchQuery"] = topic

    result = paid_api.post_json(
        endpoint,
        data=body,
        user_agent_suffix="(google_ads_transparency-adapter)",
    )

    # Polite-sleep after each call (TOS-conservative posture for reverse-engineered endpoints).
    time.sleep(POLITE_SLEEP_MS / 1000.0)

    return result


def parse_google_ads_transparency_response(
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

    # Response shape (reverse-engineered; tolerant to drift):
    # {"creatives": [...]} or {"results": [...]} or {"ads": [...]}
    ads = payload.get("creatives") or payload.get("results") or payload.get("ads") or []
    if not isinstance(ads, list):
        sys.stderr.write(
            "[google_ads_transparency] schema drift: ads field not a list; returning []\n"
        )
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for ad in ads[:limit]:
        if not isinstance(ad, dict):
            continue
        ad_id = ad.get("creativeId") or ad.get("id") or ""
        advertiser_id = ad.get("advertiserId") or ""
        advertiser_name = (ad.get("advertiserName") or ad.get("advertiserDisplayName") or "").strip()
        if not ad_id or not advertiser_name:
            continue

        creative_text_parts = []
        creative_texts = ad.get("creativeTexts") or ad.get("textContent") or []
        if isinstance(creative_texts, list):
            creative_text_parts.extend(str(t) for t in creative_texts if t)
        elif isinstance(creative_texts, str):
            creative_text_parts.append(creative_texts)

        creative_text = " · ".join(creative_text_parts)[:500]
        title_text = (creative_text_parts[0] if creative_text_parts else advertiser_name)[:200]

        ad_format = (ad.get("format") or ad.get("creativeFormat") or "").strip()
        landing_page = ad.get("landingPage") or ad.get("destinationUrl") or ""
        first_shown = ad.get("firstShown") or ad.get("firstShownDate") or ""
        last_shown = ad.get("lastShown") or ad.get("lastShownDate") or ""
        regions_raw = ad.get("regions") or ad.get("regionCodes") or []
        regions: list[str] = [str(r) for r in regions_raw] if isinstance(regions_raw, list) else []

        snippet_parts = []
        if creative_text:
            snippet_parts.append(creative_text)
        if regions:
            snippet_parts.append(f"Regions: {', '.join(regions[:5])}")
        if first_shown:
            snippet_parts.append(f"First shown: {first_shown[:10]}")
            if last_shown:
                snippet_parts.append(f"last shown: {last_shown[:10]}")
        if ad_format:
            snippet_parts.append(f"Format: {ad_format}")
        snippet = " · ".join(snippet_parts)[:500] or f"Google ad by {advertiser_name}"

        url = (
            f"https://adstransparency.google.com/advertiser/{advertiser_id}/creative/{ad_id}"
            if advertiser_id else f"https://adstransparency.google.com/creative/{ad_id}"
        )

        parsed.append({
            "id": f"google_ads:{ad_id}",
            "title": title_text,
            "snippet": snippet,
            "url": url,
            "source_domain": "adstransparency.google.com",
            "date": (first_shown[:10] if first_shown else None),
            "author": advertiser_name,
            "relevance": 0.75,
            "why_relevant": f"Google ad by {advertiser_name}" + (
                f" (matching '{query[:40]}')" if query else ""
            ),
            "metadata": {
                "ad_id": ad_id,
                "advertiser_id": advertiser_id,
                "advertiser_name": advertiser_name,
                "format": ad_format,
                "regions": regions,
                "first_shown": first_shown,
                "last_shown": last_shown,
                "landing_page": landing_page,
            },
        })
    return parsed
