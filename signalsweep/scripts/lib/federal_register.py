"""Federal Register API (signalsweep 3.15.0+).

US government rulemaking and notices. No auth required; public JSON API
maintained by federalregister.gov.

Surfaces proposed rules, final rules, notices, and presidential documents
matching a topic query. High-signal for product-safety, regulatory, and
compliance research.

Endpoint: https://www.federalregister.gov/api/v1/documents.json
Docs: federalregister.gov/developers/documentation/api/v1
"""

from __future__ import annotations

from typing import Any

from . import public_api


SEARCH_URL = "https://www.federalregister.gov/api/v1/documents.json"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_federal_register(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params: dict[str, Any] = {
        "conditions[term]": topic,
        "per_page": limit,
        "order": "newest",
        "fields[]": [
            "document_number",
            "title",
            "abstract",
            "publication_date",
            "html_url",
            "type",
            "agencies",
        ],
    }
    if from_date:
        params["conditions[publication_date][gte]"] = from_date
    if to_date:
        params["conditions[publication_date][lte]"] = to_date

    return public_api.fetch_json(
        SEARCH_URL,
        params=params,
        cache_key=f"federal_register:{topic}:{from_date}:{to_date}:{depth}",
        user_agent_suffix="(federal_register-adapter)",
    )


def parse_federal_register_response(
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
    for doc in results[:limit]:
        if not isinstance(doc, dict):
            continue
        doc_number = doc.get("document_number") or ""
        title = (doc.get("title") or "").strip()
        if not doc_number or not title:
            continue

        doc_type = doc.get("type") or "Document"
        pub_date = doc.get("publication_date") or ""
        abstract = (doc.get("abstract") or "")[:500]
        url = doc.get("html_url") or f"https://www.federalregister.gov/documents/{doc_number}"

        agencies_raw = doc.get("agencies") or []
        agency_names: list[str] = []
        if isinstance(agencies_raw, list):
            for agency in agencies_raw:
                name = agency.get("name") if isinstance(agency, dict) else (agency if isinstance(agency, str) else None)
                if name:
                    agency_names.append(name)
        agency_str = " · ".join(agency_names[:3]) if agency_names else "Unknown agency"

        parsed.append({
            "id": f"fedreg:{doc_number}",
            "title": title[:200],
            "snippet": abstract or f"{doc_type} from {agency_str}",
            "url": url,
            "source_domain": "federalregister.gov",
            "date": pub_date,
            "relevance": 0.7,
            "why_relevant": f"Federal Register {doc_type.lower()} ({agency_str[:40]})",
            "metadata": {
                "document_number": doc_number,
                "document_type": doc_type,
                "agencies": agency_names,
                "publication_date": pub_date,
            },
        })
    return parsed
