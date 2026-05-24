"""World Bank indicator catalog search (signalsweep 3.6+).

No auth. Searches the indicator catalog by topic keywords; returns indicator
metadata items. Time-series data fetch deferred to 3.6.1.
"""

from __future__ import annotations

from typing import Any

from . import public_api


INDICATOR_URL = "https://api.worldbank.org/v2/indicator"

DEPTH_LIMITS = {
    "quick": 10,
    "default": 25,
    "deep": 50,
}


def search_worldbank(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch a page of indicators; client-side filter by topic keywords."""
    per_page = 1000  # WorldBank allows big pages; we fetch once and filter locally
    params = {"format": "json", "per_page": per_page, "page": 1}
    raw = public_api.fetch_json(
        INDICATOR_URL,
        params=params,
        cache_key=f"worldbank-indicators:page1",
        user_agent_suffix="(worldbank-adapter)",
    )
    return raw


def _matches(indicator: dict[str, Any], tokens: set[str]) -> bool:
    if not tokens:
        return True
    hay = f"{indicator.get('name', '')} {indicator.get('sourceNote', '')}".lower()
    return any(tok in hay for tok in tokens)


def parse_worldbank_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    # WorldBank returns [metadata_dict, list_of_indicators]
    payload = response["items"]
    if not (isinstance(payload, list) and len(payload) >= 2):
        return []

    _meta, indicators = payload[0], payload[1]
    tokens = {t.strip().lower() for t in query.split() if len(t.strip()) >= 3}
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for ind in indicators:
        if not _matches(ind, tokens):
            continue
        iid = (ind.get("id") or "").strip()
        name = (ind.get("name") or "").strip()
        source_note = (ind.get("sourceNote") or "").strip()
        source_org = (ind.get("sourceOrganization") or "").strip()
        if not iid or not name:
            continue

        url = f"https://data.worldbank.org/indicator/{iid}"
        parsed.append({
            "id": iid,
            "title": name,
            "snippet": source_note[:500],
            "url": url,
            "date": to_date or None,
            "source_domain": "worldbank.org",
            "relevance": 0.6,
            "why_relevant": f"World Bank indicator: {name[:60]}",
            "metadata": {
                "indicator_id": iid,
                "source_organization": source_org,
                "topic_names": [(t.get("value") or "") for t in (ind.get("topics") or []) if t.get("value")],
            },
        })
        if len(parsed) >= limit:
            break
    return parsed
