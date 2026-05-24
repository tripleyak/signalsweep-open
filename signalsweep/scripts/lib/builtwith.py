"""BuiltWith tech stack lookup — envelope-first (signalsweep 3.25.0+).

Endpoint: `api.builtwith.com/v21/api.json`. Requires `BUILTWITH_API_KEY`.

Topic shape: bare domain. v3.7 paid-APIs + creds.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

ENDPOINT = "https://api.builtwith.com/v21/api.json"


def search_builtwith(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = cfg.get("BUILTWITH_API_KEY")
    if not api_key:
        return {"items": None, "error": "credentials_missing"}
    domain = topic.strip().replace("https://", "").replace("http://", "").split("/")[0].replace("www.", "")
    if not domain:
        return {"items": {"Results": [], "note": "non-domain-topic"}, "error": None}
    params = {"KEY": api_key, "LOOKUP": domain}
    return paid_api.fetch_json(ENDPOINT, params=params)


def parse_builtwith_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    payload = response["items"]
    if isinstance(payload, dict) and payload.get("note") == "non-domain-topic":
        return []
    results = payload.get("Results") or []
    if not results:
        return []
    result = results[0]
    meta = result.get("Meta") or {}
    domain = (result.get("Lookup") or meta.get("Hostname") or "").lower()
    paths = result.get("Result", {}).get("Paths") or []
    # Flatten technology counts
    tech_count = sum(len(p.get("Technologies") or []) for p in paths)
    return [{
        "id": f"builtwith:{domain}",
        "title": f"BuiltWith — {domain} · {tech_count} techs",
        "snippet": f"{tech_count} technologies detected on {domain}",
        "url": f"https://builtwith.com/{domain}",
        "source_domain": "builtwith.com",
        "date": None,
        "relevance": 0.7,
        "why_relevant": f"BuiltWith tech profile for {domain}",
        "metadata": {"platform": "builtwith", "domain": domain, "tech_count": tech_count, "paths_count": len(paths)},
    }]
