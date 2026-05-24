"""USDA NASS QuickStats agriculture statistics search (signalsweep 3.6.1+).

Auth: free `USDA_NASS_API_KEY` from quickstats.nass.usda.gov/api. Ships
with a `credentials_missing` envelope when key is absent (matches the v3.7
paid-API pattern in keepa.py / helium10.py).

QuickStats indexes USDA agricultural survey/census data: commodities,
production, prices, demographics. Returns top-N records matching the
commodity-keyed query.

Endpoint: https://quickstats.nass.usda.gov/api/api_GET/?key=<key>&commodity_desc=<query>
"""

from __future__ import annotations

from typing import Any

from . import public_api


API_URL = "https://quickstats.nass.usda.gov/api/api_GET/"

DEPTH_LIMITS = {
    "quick": 10,
    "default": 25,
    "deep": 50,
}


def search_usda_nass(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search USDA NASS for records matching the topic as commodity descriptor.

    Returns credentials_missing envelope when key absent. Uses the topic verbatim
    as `commodity_desc` filter (USDA accepts e.g. "CORN", "SOYBEANS", "WHEAT").
    """
    config = config or {}
    api_key = config.get("USDA_NASS_API_KEY") or ""
    if not api_key:
        return {"items": None, "error": "credentials_missing"}

    # NASS prefers uppercase commodity descriptors
    commodity = (topic or "").upper().strip()
    # Year filter — derive from from_date if provided
    year_from = (from_date or "")[:4] if from_date else ""

    params = {
        "key": api_key,
        "commodity_desc": commodity,
        "format": "JSON",
    }
    if year_from.isdigit():
        params["year__GE"] = year_from

    return public_api.fetch_json(
        API_URL,
        params=params,
        cache_key=f"usda_nass:{commodity}:{year_from}:{depth}",
        user_agent_suffix="(usda_nass-adapter)",
    )


def parse_usda_nass_response(
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

    records = payload.get("data") or []
    if not isinstance(records, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for r in records:
        if not isinstance(r, dict):
            continue
        commodity = (r.get("commodity_desc") or "").strip()
        statisticcat = (r.get("statisticcat_desc") or "").strip()
        unit = (r.get("unit_desc") or "").strip()
        value = (r.get("Value") or "").strip()
        year = (r.get("year") or "").strip()
        location = (r.get("location_desc") or r.get("state_name") or "").strip()
        short_desc = (r.get("short_desc") or "").strip()

        if not commodity or not value:
            continue

        # Construct a stable record id
        record_id = f"{commodity}:{statisticcat}:{year}:{location}"

        title = short_desc or f"{commodity} {statisticcat} ({year})"
        snippet = f"{value} {unit}".strip() + (f" — {location}" if location else "")

        # Link back to QuickStats for context
        url = "https://quickstats.nass.usda.gov/results"

        parsed.append({
            "id": record_id,
            "title": title[:200],
            "snippet": snippet[:500],
            "url": url,
            "date": f"{year}-12-31" if year.isdigit() else None,
            "source_domain": "nass.usda.gov",
            "relevance": 0.6,
            "why_relevant": f"USDA NASS: {commodity} {statisticcat}",
            "metadata": {
                "commodity": commodity,
                "statistic": statisticcat,
                "unit": unit,
                "value": value,
                "year": year,
                "location": location,
            },
        })
        if len(parsed) >= limit:
            break
    return parsed
