"""data.gov US catalog search via CKAN API (signalsweep 3.6+).

No auth required. Returns dataset packages matching query.
"""

from __future__ import annotations

from typing import Any

from . import public_api


SEARCH_URL = "https://catalog.data.gov/api/3/action/package_search"

DEPTH_LIMITS = {
    "quick": 10,
    "default": 25,
    "deep": 50,
}


def search_datagov(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {"q": topic, "rows": rows}
    return public_api.fetch_json(
        SEARCH_URL,
        params=params,
        cache_key=f"datagov:{topic}:{depth}",
        user_agent_suffix="(datagov-adapter)",
    )


def parse_datagov_response(response: dict[str, Any], query: str = "") -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    result = response["items"].get("result") or {}
    packages = result.get("results") or []
    parsed = []
    for pkg in packages:
        title = (pkg.get("title") or "").strip()
        notes = (pkg.get("notes") or "").strip()
        name = pkg.get("name") or ""
        org = (pkg.get("organization") or {}).get("title", "") or ""
        updated = pkg.get("metadata_modified") or pkg.get("metadata_created") or ""
        tags = [t.get("name") for t in (pkg.get("tags") or []) if t.get("name")]

        if not title or not name:
            continue

        url = f"https://catalog.data.gov/dataset/{name}"
        parsed.append({
            "id": name,
            "title": title,
            "snippet": notes[:500],
            "url": url,
            "date": (updated or "")[:10] if updated else None,
            "source_domain": "catalog.data.gov",
            "relevance": 0.6,
            "why_relevant": f"US gov dataset from {org}" if org else "US gov dataset",
            "metadata": {
                "organization": org,
                "tags": tags,
                "num_resources": len(pkg.get("resources") or []),
            },
        })
    return parsed
