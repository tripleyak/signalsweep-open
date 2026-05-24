"""Kickstarter crowdfunding campaign search (signalsweep 3.28.0+).

Surfaces crowdfunding campaigns, backer language, funding patterns, and
pre-market product concepts. Kickstarter has no official public search API;
this adapter uses the public discover JSON endpoint that powers the website.

Endpoint: https://www.kickstarter.com/discover/advanced
Returns JSON when Accept: application/json is set. 500ms polite-sleep.
Graceful degradation if endpoint structure changes.

Gated by SIGNALSWEEP_DISABLE_PUBLIC_APIS (v3.6 public-data tier).
"""

from __future__ import annotations

import time
from typing import Any

from . import public_api

DISCOVER_URL = "https://www.kickstarter.com/discover/advanced"

DEPTH_LIMITS = {"quick": 5, "default": 12, "deep": 25}
POLITE_SLEEP = 0.5


def search_kickstarter(
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
            "term": topic,
            "per_page": limit,
            "sort": "magic",
            "format": "json",
        },
        extra_headers={"Accept": "application/json"},
        cache_key=f"kickstarter:{topic}:{from_date}:{to_date}:{depth}",
        user_agent_suffix="(kickstarter-adapter)",
    )


def parse_kickstarter_response(
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
        projects = payload.get("projects") or payload.get("results") or payload.get("data") or []
    elif isinstance(payload, list):
        projects = payload
    else:
        return []

    if not isinstance(projects, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    parsed = []

    for i, proj in enumerate(projects[:limit]):
        if not isinstance(proj, dict):
            continue

        proj_id = proj.get("id") or proj.get("pid") or ""
        if not proj_id:
            continue
        proj_id = str(proj_id)

        name = (proj.get("name") or proj.get("title") or "").strip()
        if not name:
            continue

        blurb = (proj.get("blurb") or proj.get("short_blurb") or "").strip()
        slug = proj.get("slug") or ""

        category = ""
        cat_obj = proj.get("category") or {}
        if isinstance(cat_obj, dict):
            category = cat_obj.get("name") or cat_obj.get("slug") or ""
        elif isinstance(cat_obj, str):
            category = cat_obj

        pledged = _safe_number(proj, "pledged", "usd_pledged")
        goal = _safe_number(proj, "goal")
        backers = _safe_int(proj, "backers_count")
        state = (proj.get("state") or "").strip()

        urls = proj.get("urls") or {}
        web = urls.get("web") or {} if isinstance(urls, dict) else {}
        project_url = web.get("project") or "" if isinstance(web, dict) else ""
        if not project_url and slug:
            project_url = f"https://www.kickstarter.com/projects/{slug}"
        if not project_url:
            project_url = f"https://www.kickstarter.com/projects/{proj_id}"

        snippet_parts = []
        if blurb:
            snippet_parts.append(blurb[:200])
        if pledged is not None and goal is not None and goal > 0:
            snippet_parts.append(f"${pledged:,.0f} / ${goal:,.0f} ({(pledged/goal)*100:.0f}%)")
        elif pledged is not None:
            snippet_parts.append(f"${pledged:,.0f} pledged")
        if backers is not None:
            snippet_parts.append(f"{backers:,} backers")
        if state:
            snippet_parts.append(f"State: {state}")
        if category:
            snippet_parts.append(f"Category: {category}")
        snippet = " · ".join(snippet_parts) or f"Kickstarter project: {name}"

        launched = proj.get("launched_at") or proj.get("created_at") or ""
        if isinstance(launched, (int, float)):
            from datetime import datetime, timezone
            try:
                launched = datetime.fromtimestamp(launched, tz=timezone.utc).strftime("%Y-%m-%d")
            except (ValueError, OSError):
                launched = ""
        elif isinstance(launched, str) and "T" in launched:
            launched = launched.split("T")[0]

        parsed.append({
            "id": f"kickstarter:{proj_id}",
            "title": name[:200],
            "snippet": snippet[:500],
            "url": project_url,
            "source_domain": "kickstarter.com",
            "date": launched or None,
            "relevance": max(0.3, 0.8 - (i * 0.03)),
            "why_relevant": f"Kickstarter campaign for '{query[:40]}'" if query else name[:60],
            "metadata": {
                "project_id": proj_id,
                "category": category,
                "pledged": pledged,
                "goal": goal,
                "backers": backers,
                "state": state,
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
