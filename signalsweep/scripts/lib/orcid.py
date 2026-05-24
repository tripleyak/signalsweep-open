"""ORCID expanded-search for researcher records (signalsweep 3.6.1+).

No auth required for public records. Uses the public API endpoint.

Endpoint: https://pub.orcid.org/v3.0/expanded-search?q=<query>&rows=<N>
"""

from __future__ import annotations

from typing import Any

from . import public_api


SEARCH_URL = "https://pub.orcid.org/v3.0/expanded-search"

DEPTH_LIMITS = {
    "quick": 10,
    "default": 25,
    "deep": 50,
}


def search_orcid(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search ORCID public registry for researchers matching the topic."""
    rows = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {
        "q": topic,
        "rows": rows,
        "start": 0,
    }
    return public_api.fetch_json(
        SEARCH_URL,
        params=params,
        cache_key=f"orcid:{topic}:{depth}",
        user_agent_suffix="(orcid-adapter)",
        extra_headers={"Accept": "application/json"},
    )


def parse_orcid_response(
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

    results = payload.get("expanded-result") or []
    if not isinstance(results, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for r in results:
        if not isinstance(r, dict):
            continue
        orcid_id = (r.get("orcid-id") or "").strip()
        if not orcid_id:
            continue

        given = (r.get("given-names") or "").strip()
        family = (r.get("family-names") or "").strip()
        full_name = " ".join(p for p in (given, family) if p) or orcid_id

        institution_names = r.get("institution-name") or []
        if isinstance(institution_names, str):
            institution_names = [institution_names]
        institutions = [i for i in institution_names if i]
        institution_str = "; ".join(institutions[:3])

        email_list = r.get("email") or []
        if isinstance(email_list, str):
            email_list = [email_list]

        other_names = r.get("other-name") or []
        if isinstance(other_names, str):
            other_names = [other_names]

        url = f"https://orcid.org/{orcid_id}"

        parsed.append({
            "id": orcid_id,
            "title": full_name,
            "snippet": (institution_str or "ORCID researcher record")[:500],
            "url": url,
            "date": None,  # ORCID records don't have a single canonical date
            "source_domain": "orcid.org",
            "author": full_name,
            "relevance": 0.55,
            "why_relevant": f"ORCID researcher: {full_name}",
            "metadata": {
                "orcid_id": orcid_id,
                "institutions": institutions,
                "other_names": [n for n in other_names if n],
                "email_count": len(email_list),
            },
        })
        if len(parsed) >= limit:
            break
    return parsed
