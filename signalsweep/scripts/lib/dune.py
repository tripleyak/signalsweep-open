"""Dune — crypto analytics via saved query execution (signalsweep 3.22.0+).

Endpoint: `api.dune.com/api/v1/query/{query_id}/results`. Requires
`DUNE_API_KEY`. Topic shape: numeric Dune query ID.

Non-numeric topics return graceful envelope. v3.7 paid-APIs + creds.
"""

from __future__ import annotations

import re
from typing import Any

from . import paid_api

ENDPOINT_TEMPLATE = "https://api.dune.com/api/v1/query/{query_id}/results"
QUERY_ID_PATTERN = re.compile(r"^\d+$")


def _looks_like_query_id(topic: str) -> bool:
    return bool(QUERY_ID_PATTERN.match(topic.strip()))


def search_dune(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = cfg.get("DUNE_API_KEY")
    if not api_key:
        return {"items": None, "error": "credentials_missing"}
    if not _looks_like_query_id(topic):
        return {"items": {"result": {"rows": []}, "note": "non-query-id-topic"}, "error": None}
    url = ENDPOINT_TEMPLATE.format(query_id=topic.strip())
    return paid_api.fetch_json(url, extra_headers={"X-DUNE-API-KEY": api_key})


def parse_dune_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    payload = response["items"]
    if isinstance(payload, dict) and payload.get("note") == "non-query-id-topic":
        return []
    result = payload.get("result") or {}
    rows = result.get("rows") or []
    query_id = payload.get("query_id") or payload.get("execution_id") or ""
    return [{
        "id": f"dune:query:{query_id}:results",
        "title": f"Dune query {query_id} — {len(rows)} rows",
        "snippet": f"Dune Analytics query returned {len(rows)} rows of on-chain data",
        "url": f"https://dune.com/queries/{query_id}" if query_id else "https://dune.com/",
        "source_domain": "dune.com",
        "date": None,
        "relevance": 0.7,
        "why_relevant": f"Dune Analytics query {query_id} results",
        "metadata": {
            "platform": "dune",
            "query_id": query_id,
            "row_count": len(rows),
            "execution_id": payload.get("execution_id"),
        },
    }]
