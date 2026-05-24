"""CourtListener API — US court opinions and dockets (signalsweep 3.15.0+).

Free Law Project's CourtListener surfaces US court opinions (SCOTUS, federal
appellate, federal district, state courts), oral arguments, and RECAP PACER
docket entries. Free account API token required.

Auth: `COURTLISTENER_API_TOKEN` (free — register at courtlistener.com).
Envelope-first: missing token → `credentials_missing`.

Endpoint: https://www.courtlistener.com/api/rest/v3/search/?q=<query>&type=o
(type=o for opinions; type=r for dockets; type=oa for oral args.)

Docs: www.courtlistener.com/help/api/rest/
"""

from __future__ import annotations

from typing import Any

from . import paid_api


SEARCH_URL = "https://www.courtlistener.com/api/rest/v3/search/"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_courtlistener(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}

    token = config.get("COURTLISTENER_API_TOKEN") or ""
    if not token:
        return {"items": None, "error": "credentials_missing"}

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    search_type = (config.get("COURTLISTENER_SEARCH_TYPE") or "o").strip()

    params: dict[str, Any] = {
        "q": topic,
        "type": search_type,  # o=opinion, r=docket, oa=oral argument
        "order_by": "score desc",
    }
    if from_date:
        params["filed_after"] = from_date
    if to_date:
        params["filed_before"] = to_date

    result = paid_api.fetch_json(
        SEARCH_URL,
        params=params,
        cache_key=f"courtlistener:{search_type}:{topic}:{from_date}:{to_date}:{depth}",
        user_agent_suffix="(courtlistener-adapter)",
        extra_headers={"Authorization": f"Token {token}"},
    )
    # Post-filter to limit (CourtListener returns paginated results)
    if result.get("items") and isinstance(result["items"], dict):
        results = result["items"].get("results") or []
        if isinstance(results, list):
            result["items"]["results"] = results[:limit]
    return result


def parse_courtlistener_response(
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

    results = payload.get("results") or []
    if not isinstance(results, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for r in results[:limit]:
        if not isinstance(r, dict):
            continue
        # Opinions have: caseName, citation, court, dateFiled, absolute_url, snippet
        # Dockets have: caseName, docketNumber, court, dateFiled, absolute_url
        case_name = (r.get("caseName") or r.get("case_name") or "").strip()
        abs_url = r.get("absolute_url") or ""
        court = (r.get("court") or r.get("court_id") or "").strip()
        date_filed = r.get("dateFiled") or r.get("date_filed") or ""
        snippet = (r.get("snippet") or r.get("text") or "")[:500]
        citation = r.get("citation") or []
        citation_str = ", ".join(citation) if isinstance(citation, list) else str(citation or "")

        if not case_name or not abs_url:
            continue

        record_id = r.get("id") or r.get("cluster_id") or abs_url

        url = f"https://www.courtlistener.com{abs_url}" if abs_url.startswith("/") else abs_url

        parsed.append({
            "id": f"courtlistener:{record_id}",
            "title": case_name[:200],
            "snippet": snippet or f"{court} · {citation_str or 'no citation'}",
            "url": url,
            "source_domain": "courtlistener.com",
            "date": date_filed[:10] if date_filed else None,
            "relevance": 0.7,
            "why_relevant": f"Court opinion/docket matching '{query[:40]}'" if query else case_name[:60],
            "metadata": {
                "court": court,
                "citation": citation_str,
                "docket_number": r.get("docketNumber", ""),
                "filed_date": date_filed,
            },
        })
    return parsed
