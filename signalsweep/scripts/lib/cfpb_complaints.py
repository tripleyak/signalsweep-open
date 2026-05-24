"""CFPB Consumer Complaint Database (signalsweep 3.28.0+).

Consumer Financial Protection Bureau complaint data. Reveals trust/friction
patterns, complaint language, and consumer protection themes.

Endpoint: https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/
No auth required. Public API.

Gated by SIGNALSWEEP_DISABLE_PUBLIC_APIS (v3.6 public-data tier).
"""

from __future__ import annotations

from typing import Any

from . import public_api

SEARCH_URL = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/"

DEPTH_LIMITS = {"quick": 5, "default": 15, "deep": 30}


def search_cfpb_complaints(
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

    params: dict[str, Any] = {
        "search_term": topic,
        "size": limit,
        "sort": "relevance_desc",
        "format": "json",
    }
    if from_date:
        params["date_received_min"] = from_date
    if to_date:
        params["date_received_max"] = to_date

    return public_api.fetch_json(
        SEARCH_URL,
        params=params,
        cache_key=f"cfpb:{topic}:{from_date}:{to_date}:{depth}",
        user_agent_suffix="(cfpb-complaints-adapter)",
    )


def parse_cfpb_complaints_response(
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

    hits = payload.get("hits") or payload.get("results") or {}
    if isinstance(hits, dict):
        records = hits.get("hits") or []
    elif isinstance(hits, list):
        records = hits
    else:
        return []

    if not isinstance(records, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    parsed = []

    for i, hit in enumerate(records[:limit]):
        if not isinstance(hit, dict):
            continue

        src = hit.get("_source") or hit
        if not isinstance(src, dict):
            continue

        complaint_id = src.get("complaint_id") or hit.get("_id") or ""
        if not complaint_id:
            continue
        complaint_id = str(complaint_id)

        product = (src.get("product") or "").strip()
        sub_product = (src.get("sub_product") or "").strip()
        issue = (src.get("issue") or "").strip()
        sub_issue = (src.get("sub_issue") or "").strip()
        narrative = (src.get("complaint_what_happened") or "").strip()
        company = (src.get("company") or "").strip()
        state = (src.get("state") or "").strip()
        response_type = (src.get("company_response") or "").strip()
        timely = src.get("timely") or ""
        date_received = (src.get("date_received") or "").strip()

        title = issue or product or f"CFPB Complaint {complaint_id}"

        snippet_parts = []
        if product:
            snippet_parts.append(f"Product: {product}")
        if sub_product:
            snippet_parts.append(f"Sub: {sub_product}")
        if issue:
            snippet_parts.append(f"Issue: {issue}")
        if company:
            snippet_parts.append(f"Company: {company[:50]}")
        if narrative:
            snippet_parts.append(narrative[:200])
        snippet = " · ".join(snippet_parts) or "CFPB consumer complaint"

        parsed.append({
            "id": f"cfpb:{complaint_id}",
            "title": title[:200],
            "snippet": snippet[:500],
            "url": f"https://www.consumerfinance.gov/data-research/consumer-complaints/search/detail/{complaint_id}",
            "source_domain": "consumerfinance.gov",
            "date": date_received or None,
            "relevance": max(0.3, 0.7 - (i * 0.02)),
            "why_relevant": f"CFPB complaint for '{query[:40]}'" if query else title[:60],
            "metadata": {
                "complaint_id": complaint_id,
                "product": product,
                "sub_product": sub_product,
                "issue": issue,
                "sub_issue": sub_issue,
                "company": company,
                "state": state,
                "company_response": response_type,
                "timely": str(timely),
                "signal_type": "consumer_complaint",
            },
        })
    return parsed
