"""Similarweb traffic intelligence — envelope-first (signalsweep 3.25.0+).

Endpoint: `api.similarweb.com/v1/website/{domain}/total-traffic-and-engagement/visits`.
Requires `SIMILARWEB_API_KEY`. Paid-only.

Topic shape: bare domain (example.com). v3.7 paid-APIs + creds.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

ENDPOINT_TEMPLATE = "https://api.similarweb.com/v1/website/{domain}/total-traffic-and-engagement/visits"


def search_similarweb(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = cfg.get("SIMILARWEB_API_KEY")
    if not api_key:
        return {"items": None, "error": "credentials_missing"}
    domain = topic.strip().replace("https://", "").replace("http://", "").split("/")[0].replace("www.", "")
    if not domain:
        return {"items": {"visits": [], "note": "non-domain-topic"}, "error": None}
    url = ENDPOINT_TEMPLATE.format(domain=domain)
    params = {
        "api_key": api_key,
        "start_date": (from_date or "2026-01")[:7],
        "end_date": (to_date or "2026-04")[:7],
        "granularity": "monthly",
        "main_domain_only": "false",
    }
    return paid_api.fetch_json(url, params=params)


def parse_similarweb_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    payload = response["items"]
    if isinstance(payload, dict) and payload.get("note") == "non-domain-topic":
        return []
    visits = payload.get("visits") or []
    if not visits:
        return []
    domain = payload.get("meta", {}).get("request", {}).get("domain") or "unknown"
    latest = visits[-1]
    return [{
        "id": f"similarweb:{domain}:{latest.get('date', '')}",
        "title": f"Similarweb — {domain} · {latest.get('visits', 0):,} visits",
        "snippet": f"Traffic for {domain} on {latest.get('date')}: {latest.get('visits', 0):,} visits",
        "url": f"https://www.similarweb.com/website/{domain}/",
        "source_domain": "similarweb.com",
        "date": latest.get("date", "")[:10],
        "relevance": 0.7,
        "why_relevant": f"Similarweb traffic for {domain}",
        "metadata": {"platform": "similarweb", "domain": domain, "visits": latest.get("visits"), "series_length": len(visits)},
    }]
