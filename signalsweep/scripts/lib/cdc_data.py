"""CDC Data — data.cdc.gov catalog via Socrata (signalsweep 3.24.0+).

Endpoint: `api.us.socrata.com/api/catalog/v1?domains=data.cdc.gov&q={topic}`.
No auth required for low-volume. Optional `CDC_APP_TOKEN` raises rate limit.

v3.6 public-APIs tier.
"""

from __future__ import annotations

from typing import Any

from . import public_api

ENDPOINT = "https://api.us.socrata.com/api/catalog/v1"
DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_cdc_data(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not public_api.is_public_apis_enabled(cfg):
        return {"items": None, "error": "public_apis_disabled"}
    params = {"domains": "data.cdc.gov", "q": topic, "limit": DEPTH_LIMITS.get(depth, 25)}
    token = cfg.get("CDC_APP_TOKEN")
    extra_headers = {"X-App-Token": token} if token else None
    return public_api.fetch_json(ENDPOINT, params=params, extra_headers=extra_headers, user_agent_suffix="cdc-data-adapter")


def parse_cdc_data_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    results = response["items"].get("results") or []
    out = []
    for r in results:
        resource = r.get("resource") or {}
        rid = resource.get("id")
        if not rid:
            continue
        out.append({
            "id": f"cdc_data:{rid}",
            "title": (resource.get("name") or rid)[:200],
            "snippet": (resource.get("description") or "")[:500],
            "url": (r.get("permalink") or f"https://data.cdc.gov/d/{rid}"),
            "source_domain": "data.cdc.gov",
            "date": (resource.get("updatedAt") or "")[:10],
            "relevance": 0.7,
            "why_relevant": f"CDC dataset — {(resource.get('name') or rid)[:60]}",
            "metadata": {
                "platform": "cdc_data",
                "dataset_id": rid,
                "type": resource.get("type"),
                "columns_count": len(resource.get("columns_field_name") or []),
            },
        })
    return out
