"""CPSC SaferProducts.gov API (signalsweep 3.26.0+).

Consumer Product Safety Commission recall and incident data. No auth required;
fully public REST API.

Surfaces product recalls, hazard notices, and consumer incidents matching a
topic query. High-signal for product-safety, compliance, and competitive
intelligence research.

Endpoints:
  Recalls:   https://www.saferproducts.gov/RestWebServices/Recall?format=json&RecallTitle={query}
  Incidents: https://www.saferproducts.gov/RestWebServices/Incident?format=json&ProductType={query}

Docs: saferproducts.gov/RestWebServices
"""

from __future__ import annotations

from typing import Any

from . import public_api


RECALL_URL = "https://www.saferproducts.gov/RestWebServices/Recall"

DEPTH_LIMITS = {"quick": 5, "default": 15, "deep": 30}


def search_cpsc_saferproducts(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not public_api.is_public_apis_enabled(cfg):
        return {"items": None, "error": "public_apis_disabled"}

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params: dict[str, Any] = {
        "format": "json",
        "RecallTitle": topic,
    }

    return public_api.fetch_json(
        RECALL_URL,
        params=params,
        cache_key=f"cpsc:{topic}:{from_date}:{to_date}:{depth}",
        user_agent_suffix="(cpsc_saferproducts-adapter)",
    )


def parse_cpsc_saferproducts_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    payload = response["items"]
    # The CPSC API returns a JSON array directly (not wrapped in an object).
    if isinstance(payload, dict):
        # Some proxy wrappers might nest under "results".
        results = payload.get("results") or payload.get("Results") or []
    elif isinstance(payload, list):
        results = payload
    else:
        return []

    if not isinstance(results, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for rec in results[:limit]:
        if not isinstance(rec, dict):
            continue

        recall_id = rec.get("RecallID") or rec.get("RecallNumber") or ""
        if not recall_id:
            continue
        recall_id = str(recall_id)

        recall_number = str(rec.get("RecallNumber") or recall_id)
        title = (rec.get("Title") or "").strip()
        description = (rec.get("Description") or "").strip()

        if not title:
            title = f"CPSC Recall {recall_number}"

        # Build snippet from description + hazard info.
        snippet_parts = []
        if description:
            snippet_parts.append(description[:300])

        # Extract hazard info.
        hazards = rec.get("Hazards") or []
        hazard_names: list[str] = []
        hazard_types: list[str] = []
        if isinstance(hazards, list):
            for h in hazards:
                if isinstance(h, dict):
                    hname = h.get("Name") or h.get("HazardDescription") or ""
                    htype = h.get("HazardType") or h.get("HazardTypeID") or ""
                    if hname:
                        hazard_names.append(str(hname))
                    if htype:
                        hazard_types.append(str(htype))
        if hazard_names:
            snippet_parts.append(f"Hazard: {'; '.join(hazard_names[:3])}")

        snippet = " · ".join(snippet_parts) if snippet_parts else "CPSC recall record"

        # Extract product info.
        products = rec.get("Products") or []
        product_names: list[str] = []
        product_types: list[str] = []
        if isinstance(products, list):
            for p in products:
                if isinstance(p, dict):
                    pname = p.get("Name") or p.get("Description") or ""
                    ptype = p.get("Type") or ""
                    if pname:
                        product_names.append(str(pname))
                    if ptype:
                        product_types.append(str(ptype))

        # Date: RecallDate or LastPublishDate.
        recall_date = rec.get("RecallDate") or rec.get("LastPublishDate") or ""
        # Normalize YYYYMMDD → ISO if needed.
        if recall_date and len(recall_date) == 8 and recall_date.isdigit():
            recall_date = f"{recall_date[:4]}-{recall_date[4:6]}-{recall_date[6:8]}"
        # Handle ISO datetime strings (e.g. "2026-03-15T00:00:00").
        if recall_date and "T" in recall_date:
            recall_date = recall_date.split("T")[0]

        url = rec.get("URL") or f"https://www.saferproducts.gov/PublicSearch/Detail/{recall_id}"

        # Remedy and units.
        remedies = rec.get("Remedies") or []
        remedy_types: list[str] = []
        if isinstance(remedies, list):
            for r in remedies:
                if isinstance(r, dict):
                    rt = r.get("Name") or r.get("Type") or ""
                    if rt:
                        remedy_types.append(str(rt))

        units_affected = rec.get("UnitsAffected") or rec.get("NumberOfUnits") or ""

        parsed.append({
            "id": f"cpsc:{recall_id}",
            "title": title[:200],
            "snippet": snippet[:500],
            "url": url,
            "source_domain": "saferproducts.gov",
            "date": recall_date or None,
            "relevance": 0.7,
            "why_relevant": f"CPSC recall for '{query[:40]}'" if query else title[:60],
            "metadata": {
                "hazard_type": "; ".join(hazard_types[:3]) if hazard_types else "",
                "product_type": "; ".join(product_types[:3]) if product_types else "",
                "recall_date": recall_date,
                "remedy_type": "; ".join(remedy_types[:3]) if remedy_types else "",
                "units_affected": str(units_affected),
                "recall_number": recall_number,
            },
        })
    return parsed
