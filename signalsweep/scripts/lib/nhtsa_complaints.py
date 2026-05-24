"""NHTSA Vehicle Complaints (signalsweep 3.28.0+).

National Highway Traffic Safety Administration complaint data. Reveals
safety-trend patterns, failure modes, and trust barriers in automotive and
consumer products with vehicle components.

Endpoint: https://api.nhtsa.gov/complaints/complaintsBySearch
No auth required. Public API.

Gated by SIGNALSWEEP_DISABLE_PUBLIC_APIS (v3.6 public-data tier).
"""

from __future__ import annotations

from typing import Any

from . import public_api

SEARCH_URL = "https://api.nhtsa.gov/complaints/complaintsBySearch"

DEPTH_LIMITS = {"quick": 5, "default": 15, "deep": 30}


def search_nhtsa_complaints(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not public_api.is_public_apis_enabled(config):
        return {"items": None, "error": "public_apis_disabled"}

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    return public_api.fetch_json(
        SEARCH_URL,
        params={
            "searchText": topic,
            "pageSize": limit,
            "page": 1,
        },
        cache_key=f"nhtsa:{topic}:{from_date}:{to_date}:{depth}",
        user_agent_suffix="(nhtsa-complaints-adapter)",
    )


def parse_nhtsa_complaints_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    payload = response["items"]

    if isinstance(payload, dict):
        results = payload.get("results") or payload.get("complaints") or payload.get("data") or []
    elif isinstance(payload, list):
        results = payload
    else:
        return []

    if not isinstance(results, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    parsed = []

    for i, rec in enumerate(results[:limit]):
        if not isinstance(rec, dict):
            continue

        odi_number = rec.get("odiNumber") or rec.get("ODI_NUMBER") or rec.get("CMPLID") or ""
        if not odi_number:
            continue
        odi_number = str(odi_number)

        make = (rec.get("make") or rec.get("MFR_NAME") or "").strip()
        model = (rec.get("model") or rec.get("MAKETXT") or "").strip()
        year = rec.get("modelYear") or rec.get("YEARTXT") or ""
        component = (rec.get("component") or rec.get("COMPNAME") or "").strip()
        summary = (rec.get("summary") or rec.get("CDESCR") or "").strip()
        crash = rec.get("crash") or rec.get("CRASH") or ""
        fire = rec.get("fire") or rec.get("FIRE") or ""
        injuries = rec.get("numberOfInjuries") or rec.get("INJURED") or 0
        deaths = rec.get("numberOfDeaths") or rec.get("DEATHS") or 0

        title_parts = []
        if year:
            title_parts.append(str(year))
        if make:
            title_parts.append(make)
        if model:
            title_parts.append(model)
        if component:
            title_parts.append(f"— {component}")
        title = " ".join(title_parts) or f"NHTSA Complaint {odi_number}"

        snippet_parts = []
        if summary:
            snippet_parts.append(summary[:300])
        if component:
            snippet_parts.append(f"Component: {component}")
        if crash:
            snippet_parts.append(f"Crash: {crash}")
        if fire:
            snippet_parts.append(f"Fire: {fire}")
        snippet = " · ".join(snippet_parts) or "NHTSA vehicle complaint"

        date_str = rec.get("dateOfIncident") or rec.get("dateComplaintFiled") or rec.get("DATEA") or ""
        if isinstance(date_str, str) and "T" in date_str:
            date_str = date_str.split("T")[0]

        parsed.append({
            "id": f"nhtsa:{odi_number}",
            "title": title[:200],
            "snippet": snippet[:500],
            "url": f"https://www.nhtsa.gov/vehicle/{make}/{model}/complaints",
            "source_domain": "nhtsa.gov",
            "date": date_str or None,
            "relevance": max(0.3, 0.7 - (i * 0.02)),
            "why_relevant": f"NHTSA complaint for '{query[:40]}'" if query else title[:60],
            "metadata": {
                "odi_number": odi_number,
                "make": make,
                "model": model,
                "year": str(year),
                "component": component,
                "crash": str(crash),
                "fire": str(fire),
                "injuries": int(injuries) if injuries else 0,
                "deaths": int(deaths) if deaths else 0,
                "signal_type": "safety_complaint",
            },
        })
    return parsed
