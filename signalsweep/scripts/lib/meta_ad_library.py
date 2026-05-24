"""Meta Ad Library — Facebook/Instagram advertiser creative intelligence (signalsweep 3.16.0+).

Single highest-leverage source for growth marketers. Every live Facebook +
Instagram ad by every advertiser, searchable by keyword or page. Free API,
requires a Meta Developer app access token.

Two tiers of data availability (Meta's own policy):
  - **All commercial ads (any country):** creative, advertiser name, start/stop
    dates, publisher platforms. No spend/impressions/demographics.
  - **Political / issue / housing / employment / credit ads globally, AND all
    commercial ads in EU (post-DSA 2024):** add spend ranges, impressions
    ranges, demographic distribution, delivery-by-region.

For US commercial research (BirdRock / most DTC brands), tier-1 data is still
high-signal: competitor creative + page activity + run-time duration.

Auth: `META_AD_LIBRARY_ACCESS_TOKEN` — Meta Developer app user-token with
`ads_read` scope. Generate at developers.facebook.com/tools/explorer.

Config:
  `META_AD_LIBRARY_COUNTRIES` — comma-separated ISO alpha-2 (default `US`)
  `META_AD_LIBRARY_AD_TYPE`   — `ALL` (default) | `POLITICAL_AND_ISSUE_ADS`
                                | `HOUSING_ADS` | `EMPLOYMENT_ADS` | `CREDIT_ADS`
  `META_AD_LIBRARY_ACTIVE_STATUS` — `ALL` (default) | `ACTIVE` | `INACTIVE`
  `META_AD_LIBRARY_API_VERSION`   — default `v20.0`; override if Meta ships a newer Graph API version
  `META_AD_LIBRARY_SEARCH_MODE`   — `terms` (default) | `page_ids`
                                     When `page_ids`, `topic` is interpreted as a
                                     comma-separated list of page IDs.

Endpoint: https://graph.facebook.com/{version}/ads_archive

Envelope-first: missing token → `credentials_missing`.

Docs: www.facebook.com/ads/library/api/
"""

from __future__ import annotations

from typing import Any

from . import paid_api


DEFAULT_API_VERSION = "v20.0"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}

# Fields to request. Not all will be present for all ads — parser handles gracefully.
_FIELDS = [
    "id",
    "page_id",
    "page_name",
    "ad_creative_bodies",
    "ad_creative_link_titles",
    "ad_creative_link_descriptions",
    "ad_creative_link_captions",
    "ad_delivery_start_time",
    "ad_delivery_stop_time",
    "ad_snapshot_url",
    "publisher_platforms",
    "languages",
    "impressions",       # political/EU only
    "spend",             # political/EU only
    "currency",          # political/EU only
    "target_locations",  # political/EU only
]


def _endpoint(version: str) -> str:
    v = version if version.startswith("v") else f"v{version}"
    return f"https://graph.facebook.com/{v}/ads_archive"


def search_meta_ad_library(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}

    access_token = config.get("META_AD_LIBRARY_ACCESS_TOKEN") or ""
    if not access_token:
        return {"items": None, "error": "credentials_missing"}

    countries_raw = config.get("META_AD_LIBRARY_COUNTRIES") or "US"
    countries = [c.strip().upper() for c in str(countries_raw).split(",") if c.strip()]
    if not countries:
        countries = ["US"]

    ad_type = (config.get("META_AD_LIBRARY_AD_TYPE") or "ALL").strip().upper()
    active_status = (config.get("META_AD_LIBRARY_ACTIVE_STATUS") or "ALL").strip().upper()
    search_mode = (config.get("META_AD_LIBRARY_SEARCH_MODE") or "terms").strip().lower()
    api_version = (config.get("META_AD_LIBRARY_API_VERSION") or DEFAULT_API_VERSION).strip()

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    # Meta ads_archive requires list-shape params encoded as JSON-ish strings.
    # urllib will handle list→"key=a&key=b" encoding natively; Meta expects that.
    params: dict[str, Any] = {
        "access_token": access_token,
        "ad_reached_countries": f"[{','.join(repr(c) for c in countries)}]".replace("'", '"'),
        "ad_type": ad_type,
        "ad_active_status": active_status,
        "fields": ",".join(_FIELDS),
        "limit": limit,
    }
    if search_mode == "page_ids":
        # Topic interpreted as comma-separated page IDs
        page_ids = [p.strip() for p in topic.split(",") if p.strip()]
        if not page_ids:
            return {"items": None, "error": "no_page_ids_provided"}
        params["search_page_ids"] = f"[{','.join(repr(p) for p in page_ids)}]".replace("'", '"')
    else:
        params["search_terms"] = topic

    # Date window is available but scope is "ad delivery dates," not "results from within window"
    # — documented but rarely useful for search-terms-based queries. We omit unless user pushes.

    return paid_api.fetch_json(
        _endpoint(api_version),
        params=params,
        cache_key=None,  # avoid caching token-bearing URLs
        user_agent_suffix="(meta_ad_library-adapter)",
    )


def parse_meta_ad_library_response(
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

    ads = payload.get("data") or []
    if not isinstance(ads, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for ad in ads[:limit]:
        if not isinstance(ad, dict):
            continue
        ad_id = ad.get("id") or ""
        page_id = ad.get("page_id") or ""
        page_name = (ad.get("page_name") or "").strip()
        if not ad_id or not page_name:
            continue

        # Ad creative — concatenate bodies + titles into searchable snippet
        bodies = ad.get("ad_creative_bodies") or []
        titles = ad.get("ad_creative_link_titles") or []
        descs = ad.get("ad_creative_link_descriptions") or []
        creative_parts = []
        if isinstance(titles, list):
            creative_parts.extend(str(t) for t in titles if t)
        if isinstance(bodies, list):
            creative_parts.extend(str(b) for b in bodies if b)
        if isinstance(descs, list):
            creative_parts.extend(str(d) for d in descs if d)
        creative_text = " · ".join(creative_parts)[:500] or f"Ad from {page_name}"

        # Title: first non-empty of titles > bodies > f"{page_name} ad"
        title_text = ""
        if isinstance(titles, list) and titles:
            title_text = str(titles[0])
        elif isinstance(bodies, list) and bodies:
            title_text = str(bodies[0])
        if not title_text:
            title_text = f"{page_name} — ad {ad_id[:12]}"
        title_text = title_text[:200]

        # Duration — days active
        start = ad.get("ad_delivery_start_time", "") or ""
        stop = ad.get("ad_delivery_stop_time", "") or ""

        platforms_raw = ad.get("publisher_platforms") or []
        platforms: list[str] = [str(p).lower() for p in platforms_raw] if isinstance(platforms_raw, list) else []

        # Spend/impressions ranges (political/EU only)
        spend_obj = ad.get("spend") or {}
        impressions_obj = ad.get("impressions") or {}
        spend_range = ""
        if isinstance(spend_obj, dict) and spend_obj.get("lower_bound"):
            lo = spend_obj.get("lower_bound")
            hi = spend_obj.get("upper_bound") or "?"
            spend_range = f"${lo}-{hi}"
        impr_range = ""
        if isinstance(impressions_obj, dict) and impressions_obj.get("lower_bound"):
            lo = impressions_obj.get("lower_bound")
            hi = impressions_obj.get("upper_bound") or "?"
            impr_range = f"{lo}-{hi}"

        # Snippet synthesis
        snippet_parts = []
        if platforms:
            snippet_parts.append(f"Platforms: {', '.join(platforms)}")
        if start:
            snippet_parts.append(f"Started {start[:10]}")
            if stop:
                snippet_parts.append(f"stopped {stop[:10]}")
        if spend_range:
            snippet_parts.append(f"Spend: {spend_range}")
        if impr_range:
            snippet_parts.append(f"Impressions: {impr_range}")
        snippet_meta = " · ".join(snippet_parts)
        snippet = f"{creative_text}\n\n{snippet_meta}"[:500] if snippet_meta else creative_text

        url = ad.get("ad_snapshot_url") or f"https://www.facebook.com/ads/library/?id={ad_id}"

        parsed.append({
            "id": f"meta_ad:{ad_id}",
            "title": title_text,
            "snippet": snippet,
            "url": url,
            "source_domain": "facebook.com",
            "date": (start[:10] if start else None),
            "author": page_name,
            "relevance": 0.75,
            "why_relevant": f"Meta ad by {page_name}" + (f" (matching '{query[:40]}')" if query else ""),
            "metadata": {
                "ad_id": ad_id,
                "page_id": page_id,
                "page_name": page_name,
                "platforms": platforms,
                "delivery_start": start,
                "delivery_stop": stop,
                "spend_range": spend_range,
                "impressions_range": impr_range,
                "currency": ad.get("currency", ""),
                "languages": ad.get("languages", []),
                "creative_body_count": len(bodies) if isinstance(bodies, list) else 0,
            },
        })
    return parsed
