"""IMF data services dataflow search (signalsweep 3.6.1+).

No auth required. Fetches the IMF SDMX-JSON dataflow listing once and
filters client-side by topic keywords. Mirrors worldbank.py's
"fetch index, filter locally" pattern.

Endpoint: https://dataservices.imf.org/REST/SDMX_JSON.svc/Dataflow/
"""

from __future__ import annotations

from typing import Any

from . import public_api


DATAFLOW_URL = "https://dataservices.imf.org/REST/SDMX_JSON.svc/Dataflow/"

DEPTH_LIMITS = {
    "quick": 10,
    "default": 25,
    "deep": 50,
}


def search_imf(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch IMF dataflow index. Filtering by topic happens at parse time."""
    return public_api.fetch_json(
        DATAFLOW_URL,
        params=None,
        cache_key="imf:dataflow-index",
        user_agent_suffix="(imf-adapter)",
    )


def _matches(dataflow: dict[str, Any], tokens: set[str]) -> bool:
    if not tokens:
        return True
    name_field = dataflow.get("Name") or {}
    if isinstance(name_field, dict):
        name = (name_field.get("#text") or "").lower()
    else:
        name = str(name_field).lower()
    return any(tok in name for tok in tokens)


def parse_imf_response(
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

    structure = payload.get("Structure") or {}
    dataflows_container = structure.get("Dataflows") or {}
    dataflow_list = dataflows_container.get("Dataflow") or []
    if isinstance(dataflow_list, dict):
        # Single dataflow returned as object instead of list
        dataflow_list = [dataflow_list]

    tokens = {t.strip().lower() for t in query.split() if len(t.strip()) >= 3}
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for df in dataflow_list:
        if not isinstance(df, dict):
            continue
        if not _matches(df, tokens):
            continue
        df_id = (df.get("@id") or "").strip()
        agency = (df.get("@agencyID") or "").strip()
        name_field = df.get("Name") or {}
        if isinstance(name_field, dict):
            name = (name_field.get("#text") or "").strip()
        else:
            name = str(name_field).strip()

        if not df_id or not name:
            continue

        # IMF dataflow landing pages
        url = f"https://data.imf.org/regular.aspx?key={df_id}"

        parsed.append({
            "id": df_id,
            "title": name,
            "snippet": f"IMF dataflow {df_id}" + (f" ({agency})" if agency else ""),
            "url": url,
            "date": to_date or None,
            "source_domain": "imf.org",
            "relevance": 0.6,
            "why_relevant": f"IMF dataset: {name[:60]}",
            "metadata": {
                "dataflow_id": df_id,
                "agency": agency,
            },
        })
        if len(parsed) >= limit:
            break
    return parsed
