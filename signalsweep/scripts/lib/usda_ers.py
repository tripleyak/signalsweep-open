"""USDA Economic Research Service API (signalsweep 3.24.0+).

Endpoint family: `api.ers.usda.gov/data/arms/` + sibling endpoints. Requires
`USDA_ERS_API_KEY`. Envelope-first.

Complements v3.6.1 `usda_nass` (QuickStats agriculture data). v3.7 paid-APIs + creds.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

ENDPOINT = "https://api.ers.usda.gov/data/arms/surveydata"


def search_usda_ers(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = cfg.get("USDA_ERS_API_KEY")
    if not api_key:
        return {"items": None, "error": "credentials_missing"}
    # ERS ARMS endpoint requires structured query (reportName etc). We ship
    # a placeholder envelope when the topic isn't a structured ARMS query.
    # Users configure `USDA_ERS_REPORT_NAME` for targeted pulls.
    report = cfg.get("USDA_ERS_REPORT_NAME")
    if not report:
        return {"items": {"data": [], "note": "report_name_required"}, "error": None}
    params = {"api_key": api_key, "reportName": report}
    return paid_api.fetch_json(ENDPOINT, params=params)


def parse_usda_ers_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    payload = response["items"]
    if isinstance(payload, dict) and payload.get("note") == "report_name_required":
        return []
    data = payload.get("data") or []
    if not data:
        return []
    return [{
        "id": f"usda_ers:arms:{payload.get('reportName', 'report')}",
        "title": f"USDA ERS ARMS — {payload.get('reportName', 'report')} ({len(data)} rows)",
        "snippet": f"ARMS survey data, {len(data)} records",
        "url": "https://www.ers.usda.gov/data-products/",
        "source_domain": "ers.usda.gov",
        "date": None,
        "relevance": 0.7,
        "why_relevant": "USDA Economic Research ARMS survey",
        "metadata": {"platform": "usda_ers", "report_name": payload.get("reportName"), "row_count": len(data)},
    }]
