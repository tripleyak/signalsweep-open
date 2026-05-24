"""Crunchbase company/funding search — envelope-first (signalsweep 3.25.0+).

Endpoint: `api.crunchbase.com/api/v4/searches/organizations`. Requires
`CRUNCHBASE_API_KEY`. Paid-only; ships envelope-first.

v3.7 paid-APIs + creds.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

ENDPOINT = "https://api.crunchbase.com/api/v4/searches/organizations"


def search_crunchbase(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = cfg.get("CRUNCHBASE_API_KEY")
    if not api_key:
        return {"items": None, "error": "credentials_missing"}
    body = {
        "field_ids": ["name", "short_description", "website_url", "categories"],
        "query": [{"type": "predicate", "field_id": "name", "operator_id": "contains", "values": [topic]}],
        "limit": 25,
    }
    return paid_api.post_json(ENDPOINT, json_body=body, extra_headers={"X-cb-user-key": api_key})


def parse_crunchbase_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    entities = response["items"].get("entities") or []
    out = []
    for e in entities:
        props = e.get("properties") or {}
        name = props.get("name") or e.get("uuid")
        if not name:
            continue
        out.append({
            "id": f"crunchbase:{e.get('uuid', name)}",
            "title": name,
            "snippet": (props.get("short_description") or "")[:500],
            "url": props.get("website_url") or f"https://www.crunchbase.com/organization/{name.lower().replace(' ', '-')}",
            "source_domain": "crunchbase.com",
            "date": None,
            "relevance": 0.7,
            "why_relevant": f"Crunchbase — {name}",
            "metadata": {"platform": "crunchbase", "uuid": e.get("uuid"), "categories": props.get("categories") or []},
        })
    return out
