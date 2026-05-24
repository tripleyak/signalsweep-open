"""US Bureau of Economic Analysis dataset search (signalsweep 3.6.1+).

Auth: free `BEA_API_KEY` from apps.bea.gov/API/signup. Ships with a
`credentials_missing` envelope when key is absent (matches the v3.7
paid-API pattern in keepa.py / helium10.py).

For v3.6.1, surfaces the BEA dataset listing filtered by query tokens
client-side. Time-series data fetch deferred to v3.6.2.

Endpoint: https://apps.bea.gov/api/data?UserID=<key>&method=GETDATASETLIST
"""

from __future__ import annotations

from typing import Any

from . import public_api


API_URL = "https://apps.bea.gov/api/data"

DEPTH_LIMITS = {
    "quick": 10,
    "default": 25,
    "deep": 50,
}


def search_bea(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch BEA dataset listing. Returns credentials_missing envelope when key absent."""
    config = config or {}
    api_key = config.get("BEA_API_KEY") or ""
    if not api_key:
        return {"items": None, "error": "credentials_missing"}

    params = {
        "UserID": api_key,
        "method": "GETDATASETLIST",
        "ResultFormat": "JSON",
    }
    return public_api.fetch_json(
        API_URL,
        params=params,
        cache_key="bea:dataset-list",
        user_agent_suffix="(bea-adapter)",
    )


def _matches(dataset: dict[str, Any], tokens: set[str]) -> bool:
    if not tokens:
        return True
    name = (dataset.get("DatasetName") or "").lower()
    desc = (dataset.get("DatasetDescription") or "").lower()
    hay = f"{name} {desc}"
    return any(tok in hay for tok in tokens)


def parse_bea_response(
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

    bea_api = payload.get("BEAAPI") or {}
    results = bea_api.get("Results") or {}
    datasets = results.get("Dataset") or []
    if isinstance(datasets, dict):
        datasets = [datasets]

    tokens = {t.strip().lower() for t in query.split() if len(t.strip()) >= 3}
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for ds in datasets:
        if not isinstance(ds, dict):
            continue
        if not _matches(ds, tokens):
            continue
        ds_name = (ds.get("DatasetName") or "").strip()
        ds_desc = (ds.get("DatasetDescription") or "").strip()
        if not ds_name:
            continue

        url = f"https://apps.bea.gov/iTable/?reqid={ds_name}"

        parsed.append({
            "id": ds_name,
            "title": ds_desc or ds_name,
            "snippet": ds_desc[:500],
            "url": url,
            "date": to_date or None,
            "source_domain": "bea.gov",
            "relevance": 0.6,
            "why_relevant": f"BEA dataset: {ds_name}",
            "metadata": {
                "dataset_name": ds_name,
            },
        })
        if len(parsed) >= limit:
            break
    return parsed
