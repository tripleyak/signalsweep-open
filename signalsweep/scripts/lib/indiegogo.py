"""Indiegogo crowdfunding campaign search (signalsweep 3.28.0+).

Surfaces crowdfunding campaigns, backer counts, funding progress, and
category trends. Reveals pre-market willingness to pay and early product
concepts before mass-market availability.

Endpoint: https://www.indiegogo.com/private_api/discover
Public JSON endpoint (no auth required). 500ms polite-sleep.
Graceful degradation if endpoint structure changes.

Gated by SIGNALSWEEP_DISABLE_PUBLIC_APIS (v3.6 public-data tier).
"""

from __future__ import annotations

import time
from typing import Any

from . import public_api

DISCOVER_URL = "https://www.indiegogo.com/private_api/discover"
SEARCH_URL = "https://www.indiegogo.com/private_api/discover/search"

DEPTH_LIMITS = {"quick": 5, "default": 12, "deep": 25}
POLITE_SLEEP = 0.5


def search_indiegogo(
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

    time.sleep(POLITE_SLEEP)

    return public_api.fetch_json(
        DISCOVER_URL,
        params={
            "q": topic,
            "per_page": limit,
            "sort": "trending",
        },
        cache_key=f"indiegogo:{topic}:{from_date}:{to_date}:{depth}",
        user_agent_suffix="(indiegogo-adapter)",
    )


def parse_indiegogo_response(
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
        campaigns = payload.get("response") or payload.get("campaigns") or payload.get("results") or []
    elif isinstance(payload, list):
        campaigns = payload
    else:
        return []

    if not isinstance(campaigns, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    parsed = []

    for i, camp in enumerate(campaigns[:limit]):
        if not isinstance(camp, dict):
            continue

        camp_id = camp.get("id") or camp.get("campaign_id") or ""
        if not camp_id:
            continue
        camp_id = str(camp_id)

        title = (camp.get("title") or camp.get("name") or "").strip()
        if not title:
            continue

        tagline = (camp.get("tagline") or camp.get("blurb") or camp.get("short_description") or "").strip()
        category = (camp.get("category_name") or camp.get("category") or "").strip()

        funds_raised = _safe_number(camp, "collected_funds", "funds_raised_amount", "amount_raised")
        goal = _safe_number(camp, "goal", "funding_goal", "goal_amount")
        backers = _safe_int(camp, "contributions_count", "backers_count", "number_of_backers")
        pct_funded = _safe_number(camp, "percent_funded", "funding_percentage")

        slug = camp.get("slug") or camp.get("web_url") or ""
        if slug and not slug.startswith("http"):
            url = f"https://www.indiegogo.com/projects/{slug}"
        elif slug.startswith("http"):
            url = slug
        else:
            url = f"https://www.indiegogo.com/projects/{camp_id}"

        snippet_parts = []
        if tagline:
            snippet_parts.append(tagline[:200])
        if funds_raised is not None and goal is not None and goal > 0:
            snippet_parts.append(f"${funds_raised:,.0f} / ${goal:,.0f} ({(funds_raised/goal)*100:.0f}%)")
        elif funds_raised is not None:
            snippet_parts.append(f"${funds_raised:,.0f} raised")
        if backers is not None:
            snippet_parts.append(f"{backers:,} backers")
        if category:
            snippet_parts.append(f"Category: {category}")
        snippet = " · ".join(snippet_parts) or f"Indiegogo campaign: {title}"

        open_date = camp.get("open_date") or camp.get("launched_at") or camp.get("created_at") or ""
        if open_date and "T" in str(open_date):
            open_date = str(open_date).split("T")[0]

        parsed.append({
            "id": f"indiegogo:{camp_id}",
            "title": title[:200],
            "snippet": snippet[:500],
            "url": url,
            "source_domain": "indiegogo.com",
            "date": open_date or None,
            "relevance": max(0.3, 0.8 - (i * 0.03)),
            "why_relevant": f"Indiegogo crowdfunding for '{query[:40]}'" if query else title[:60],
            "metadata": {
                "campaign_id": camp_id,
                "category": category,
                "funds_raised": funds_raised,
                "goal": goal,
                "percent_funded": pct_funded,
                "backers": backers,
                "signal_type": "crowdfunding",
            },
        })
    return parsed


def _safe_number(d: dict, *keys: str) -> float | None:
    for k in keys:
        v = d.get(k)
        if v is not None:
            try:
                return float(str(v).replace(",", "").replace("$", "").strip())
            except (ValueError, TypeError):
                pass
    return None


def _safe_int(d: dict, *keys: str) -> int | None:
    for k in keys:
        v = d.get(k)
        if v is not None:
            try:
                return int(str(v).replace(",", "").strip())
            except (ValueError, TypeError):
                pass
    return None
