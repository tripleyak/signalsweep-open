"""SEC XBRL company facts (signalsweep 3.18.0+).

Complements v3.6 `sec_edgar` (filings catalog) with structured financial facts
from the XBRL tag dataset. Endpoint: `data.sec.gov/api/xbrl/companyfacts/CIK{10-digit}.json`.

No auth required; SEC asks for `User-Agent` identifying your contact email.
Gated by v3.6 public-APIs toggle. Topic can be a CIK number or ticker-like
string — numeric topics treated as CIK directly; alpha topics require a
prior `sec_edgar`-style company search (deferred to future version for now
we return the XBRL companyfacts structure for numeric CIK inputs only).
"""

from __future__ import annotations

import re
from typing import Any

from . import financial_markets, public_api

ENDPOINT_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
CIK_PATTERN = re.compile(r"^\d{1,10}$")


def _looks_like_cik(topic: str) -> bool:
    return bool(CIK_PATTERN.match(topic.strip()))


def _pad_cik(cik: str) -> str:
    return cik.strip().zfill(10)


def search_sec_xbrl(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not public_api.is_public_apis_enabled(cfg):
        return {"items": None, "error": "public_apis_disabled"}
    if not _looks_like_cik(topic):
        # Non-CIK topics graceful-degrade: return empty companyfacts envelope
        # with note (adapter is CIK-targeted; pair with sec_edgar for lookup).
        return {
            "items": {"cik": "", "facts": {}, "note": "non-cik-topic"},
            "error": None,
        }
    cik = _pad_cik(topic)
    url = ENDPOINT_TEMPLATE.format(cik=cik)
    return public_api.fetch_json(
        url,
        user_agent_suffix="sec-xbrl-adapter",
        cache_key=f"sec_xbrl:{cik}",
    )


def parse_sec_xbrl_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    facts_payload = response["items"]
    if facts_payload.get("note") == "non-cik-topic":
        return []
    cik = facts_payload.get("cik") or ""
    entity_name = facts_payload.get("entityName") or f"CIK {cik}"
    facts = facts_payload.get("facts") or {}
    # Surface a summary item + top-level fact counts rather than emitting
    # thousands of tag items. Keep summary bounded.
    total_tags = 0
    for namespace in facts.values():
        if isinstance(namespace, dict):
            total_tags += len(namespace)
    if not total_tags:
        return []
    return [
        financial_markets.build_financial_item(
            item_id=f"sec_xbrl:{cik}:companyfacts",
            platform="sec_xbrl",
            title=f"{entity_name} — SEC XBRL companyfacts",
            snippet=f"{total_tags} XBRL fact tags across us-gaap + dei taxonomies",
            url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}",
            source_domain="sec.gov",
            asset_type="companyfacts",
            symbol=f"CIK{int(cik)}",
            currency="USD",
            relevance=0.75,
            why_relevant=f"SEC XBRL fact tags for {entity_name}",
            extra_metadata={
                "cik": cik,
                "total_fact_tags": total_tags,
                "entity_name": entity_name,
            },
        )
    ]
