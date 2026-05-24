"""USPTO patents via Open Data Portal API (signalsweep 3.15.0+).

USPTO Open Data Portal (ODP) provides free patent application search.
Requires a USPTO.gov account + ID.me verification to obtain an API key.

Returns US patent applications matching query with title, inventors,
assignees, and filing dates. High-signal for competitive IP research,
freedom-to-operate queries, and tracking a company's patent portfolio.

Auth: `PATENTSVIEW_API_KEY` header (`X-API-KEY`). Envelope-first.

Endpoint: https://api.uspto.gov/api/v1/patent/applications/search
Method: GET with query-string params.

Docs: data.uspto.gov/apis/getting-started
"""

from __future__ import annotations

from typing import Any

from . import paid_api


SEARCH_URL = "https://api.uspto.gov/api/v1/patent/applications/search"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_uspto_patents(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}

    api_key = config.get("PATENTSVIEW_API_KEY") or ""
    if not api_key:
        return {"items": None, "error": "credentials_missing"}

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    params: dict[str, Any] = {
        "query": topic,
        "rows": limit,
        "start": 0,
    }
    if from_date:
        params["filingStartDate"] = from_date
    if to_date:
        params["filingEndDate"] = to_date

    return paid_api.fetch_json(
        SEARCH_URL,
        params=params,
        user_agent_suffix="(uspto_patents-adapter)",
        extra_headers={"X-API-KEY": api_key},
    )


def parse_uspto_patents_response(
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

    applications = payload.get("patentFileWrapperDataBag") or []
    if not isinstance(applications, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for app in applications[:limit]:
        if not isinstance(app, dict):
            continue
        meta = app.get("applicationMetaData") or {}
        if not isinstance(meta, dict):
            continue

        title = (meta.get("inventionTitle") or "").strip()
        if not title:
            continue

        app_number = meta.get("applicationNumberText") or meta.get("applicationConfirmationNumber") or ""
        filing_date = meta.get("filingDate") or meta.get("effectiveFilingDate") or ""

        assignee = meta.get("firstApplicantName") or ""
        inventor = meta.get("firstInventorName") or ""

        inventor_names = []
        for inv in (meta.get("inventorBag") or []):
            if isinstance(inv, dict):
                nm = inv.get("inventorNameText") or ""
                if nm:
                    inventor_names.append(nm)

        status = meta.get("applicationStatusDescriptionText") or ""
        app_type = meta.get("applicationTypeLabelName") or ""

        app_id = str(app_number) if app_number else title[:20].replace(" ", "-")

        parsed.append({
            "id": f"uspto:{app_id}",
            "title": title[:200],
            "snippet": f"{app_type} application by {assignee or inventor or 'Unknown'}. Status: {status}" if status else f"{app_type} patent application",
            "url": f"https://patents.google.com/patent/US{app_id}" if app_number else "",
            "source_domain": "uspto.gov",
            "date": filing_date[:10] if filing_date else None,
            "author": (assignee or inventor or None),
            "relevance": 0.7,
            "why_relevant": f"USPTO patent match for '{query[:40]}'" if query else title[:60],
            "metadata": {
                "application_number": str(app_number),
                "assignee": assignee,
                "inventors": inventor_names[:5],
                "filing_date": filing_date,
                "status": status,
                "type": app_type,
            },
        })
    return parsed
