"""Eurostat dataset catalog (signalsweep 3.6+).

No auth required. The Eurostat data browser exposes a catalog via the TOC
(table of contents) endpoint. We filter matching datasets client-side.

MVP: returns catalog metadata items. Full dataset value fetch deferred to 3.6.1.
"""

from __future__ import annotations

from typing import Any

from . import public_api


# The Eurostat TOC provides dataset-level metadata in a hierarchical tree.
# Simpler for MVP: curated list of high-value Eurostat dataset codes
# keyed by topic tags. Extend in 3.6.1.
CURATED_DATASETS = [
    {"code": "prc_hicp_manr", "title": "Harmonised Index of Consumer Prices (HICP) — monthly annual rate", "topic_tags": ["inflation", "cpi", "hicp", "consumer prices"]},
    {"code": "une_rt_m", "title": "EU Unemployment Rate (monthly)", "topic_tags": ["unemployment", "jobless"]},
    {"code": "namq_10_gdp", "title": "Quarterly GDP at current prices (EU, Euro area)", "topic_tags": ["gdp", "growth", "economy"]},
    {"code": "demo_gind", "title": "Demographic balance and crude rates (EU population)", "topic_tags": ["population", "demographics", "births", "deaths"]},
    {"code": "migr_imm1ctz", "title": "Immigration by citizenship (EU)", "topic_tags": ["immigration", "migration"]},
    {"code": "ei_bcs_cs", "title": "Consumer confidence indicator (monthly)", "topic_tags": ["consumer confidence", "sentiment"]},
    {"code": "tour_occ_arm", "title": "Tourist nights spent at accommodation establishments", "topic_tags": ["tourism", "travel"]},
    {"code": "sdg_07_11", "title": "Share of renewable energy in gross final energy consumption", "topic_tags": ["renewable", "energy", "climate"]},
]


def _matches(dataset: dict[str, Any], topic: str) -> bool:
    t = topic.lower()
    return any(tag in t for tag in dataset.get("topic_tags", []))


def search_eurostat(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    matches = [d for d in CURATED_DATASETS if _matches(d, topic)]
    return {"items": {"matches": matches}, "error": None}


def parse_eurostat_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    matches = response["items"].get("matches") or []
    parsed = []
    for d in matches:
        code = d["code"]
        parsed.append({
            "id": code,
            "title": d["title"],
            "snippet": f"Eurostat dataset {code}. Time-series at ec.europa.eu/eurostat/databrowser.",
            "url": f"https://ec.europa.eu/eurostat/databrowser/view/{code}/default/table",
            "date": to_date or None,
            "source_domain": "eurostat.ec.europa.eu",
            "relevance": 0.6,
            "why_relevant": f"Eurostat: {d['title'][:60]}",
            "metadata": {
                "dataset_code": code,
                "tags": d.get("topic_tags", []),
            },
        })
    return parsed
