"""openFDA API (signalsweep 3.15.0+, CAERS expansion 3.28.0+).

FDA's public API covering drug adverse events, device recalls, food recalls,
food/supplement/cosmetic adverse events (CAERS), and labeling data. No auth
required for basic use (1k calls/day rate limit); optional free API key raises
limit to 120k/day.

Endpoint: https://api.fda.gov/{endpoint}/{dataset}.json
Default dataset: drug/event (adverse-event reports).
Override via OPENFDA_DATASET env var. Key datasets:
  drug/event — drug adverse events (default)
  food/event — CAERS: food, supplement, cosmetic adverse events
  food/enforcement — food recalls
  device/event — device adverse events
  device/recall — device recalls

v3.28.0: Added CAERS-specific field parsing for food/event dataset
(supplement tolerance, dosage confusion, packaging defects).

Docs: open.fda.gov/apis
"""

from __future__ import annotations

from typing import Any

from . import public_api


DEFAULT_DATASET = "drug/event"

MULTI_DATASETS = ["drug/event", "food/event"]

SEARCH_URL_TEMPLATE = "https://api.fda.gov/{dataset}.json"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_fda_openfda(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    dataset = (config.get("OPENFDA_DATASET") or DEFAULT_DATASET).strip()
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    quoted_topic = f'"{topic}"' if " " in topic else topic
    params: dict[str, Any] = {
        "search": quoted_topic,
        "limit": limit,
    }
    api_key = config.get("OPENFDA_API_KEY") or ""
    if api_key:
        params["api_key"] = api_key

    result = public_api.fetch_json(
        SEARCH_URL_TEMPLATE.format(dataset=dataset),
        params=params,
        cache_key=f"openfda:{dataset}:{topic}:{depth}",
        user_agent_suffix="(fda_openfda-adapter)",
    )

    if depth in ("default", "deep") and dataset == DEFAULT_DATASET:
        caers_result = public_api.fetch_json(
            SEARCH_URL_TEMPLATE.format(dataset="food/event"),
            params={**params, "limit": min(limit, 10)},
            cache_key=f"openfda:food/event:{topic}:{depth}",
            user_agent_suffix="(fda_openfda-caers-adapter)",
        )
        if not result.get("error"):
            result["_caers"] = caers_result

    result["_dataset"] = dataset
    return result


def parse_fda_openfda_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    dataset = response.get("_dataset") or DEFAULT_DATASET
    payload = response["items"]
    if not isinstance(payload, dict):
        return []

    results = payload.get("results") or []
    if not isinstance(results, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for i, rec in enumerate(results[:limit]):
        if not isinstance(rec, dict):
            continue

        # openFDA record shapes vary by dataset. We extract best-effort:
        # - drug/event: safetyreportid, patient.drug[].medicinalproduct, patient.reaction[].reactionmeddrapt
        # - drug/enforcement: recall_number, product_description, reason_for_recall
        # - device/recall: k_number / recall_number, product_description, reason_for_recall
        # - food/enforcement: recall_number, product_description, reason_for_recall

        record_id = (
            rec.get("safetyreportid")
            or rec.get("recall_number")
            or rec.get("k_number")
            or rec.get("report_number")
            or f"rec_{i}"
        )

        # Title candidates in priority order.
        title = ""
        if "product_description" in rec and rec["product_description"]:
            title = str(rec["product_description"])[:200]
        elif "openfda" in rec and isinstance(rec["openfda"], dict):
            brand = rec["openfda"].get("brand_name") or []
            if isinstance(brand, list) and brand:
                title = str(brand[0])
        elif "patient" in rec and isinstance(rec["patient"], dict):
            drugs = rec["patient"].get("drug") or []
            if isinstance(drugs, list) and drugs:
                drug0 = drugs[0] if isinstance(drugs[0], dict) else {}
                title = str(drug0.get("medicinalproduct", ""))[:200]

        if not title:
            title = f"openFDA record {record_id}"

        # Snippet: reason / reaction / status summary.
        snippet_parts = []
        if rec.get("reason_for_recall"):
            snippet_parts.append(f"Reason: {rec['reason_for_recall'][:200]}")
        if rec.get("classification"):
            snippet_parts.append(f"Class: {rec['classification']}")
        if rec.get("status"):
            snippet_parts.append(f"Status: {rec['status']}")
        if isinstance(rec.get("patient"), dict):
            reactions = (rec["patient"].get("reaction") or [])
            if isinstance(reactions, list) and reactions:
                r0 = reactions[0].get("reactionmeddrapt") if isinstance(reactions[0], dict) else None
                if r0:
                    snippet_parts.append(f"Reaction: {r0}")
        snippet = " · ".join(snippet_parts) if snippet_parts else "openFDA record"

        # Date candidates.
        record_date = (
            rec.get("report_date")
            or rec.get("recall_initiation_date")
            or rec.get("event_date_initiated")
            or rec.get("receivedate")
            or ""
        )
        # openFDA date format is YYYYMMDD; normalize to ISO.
        if record_date and len(record_date) == 8 and record_date.isdigit():
            record_date = f"{record_date[:4]}-{record_date[4:6]}-{record_date[6:8]}"

        parsed.append({
            "id": f"openfda:{record_id}",
            "title": title[:200],
            "snippet": snippet[:500],
            "url": f"https://open.fda.gov/apis/{record_id}",
            "source_domain": "fda.gov",
            "date": record_date or None,
            "relevance": 0.7,
            "why_relevant": f"FDA record for '{query[:40]}'" if query else title[:60],
            "metadata": {
                "record_id": record_id,
                "dataset": dataset,
                "classification": rec.get("classification", ""),
                "recall_number": rec.get("recall_number", ""),
            },
        })

    caers_data = response.get("_caers")
    if caers_data and not caers_data.get("error") and caers_data.get("items"):
        caers_items = _parse_caers_results(caers_data["items"], query, depth)
        parsed.extend(caers_items)

    return parsed


def _parse_caers_results(
    payload: Any,
    query: str,
    depth: str,
) -> list[dict[str, Any]]:
    """Parse CAERS food/event records into normalized items."""
    if not isinstance(payload, dict):
        return []

    results = payload.get("results") or []
    if not isinstance(results, list):
        return []

    parsed = []
    for i, rec in enumerate(results[:10]):
        if not isinstance(rec, dict):
            continue

        report_id = rec.get("report_number") or f"caers_{i}"

        products = rec.get("products") or []
        product_names = []
        product_roles = []
        if isinstance(products, list):
            for p in products:
                if isinstance(p, dict):
                    nm = p.get("name_brand") or p.get("industry_name") or ""
                    if nm:
                        product_names.append(str(nm).strip()[:100])
                    role = p.get("role") or ""
                    if role:
                        product_roles.append(str(role).strip())

        title = product_names[0] if product_names else f"CAERS report {report_id}"

        reactions = rec.get("reactions") or []
        reaction_list = []
        if isinstance(reactions, list):
            for r in reactions:
                if isinstance(r, str):
                    reaction_list.append(r)

        outcomes = rec.get("outcomes") or []
        outcome_list = []
        if isinstance(outcomes, list):
            for o in outcomes:
                if isinstance(o, str):
                    outcome_list.append(o)

        snippet_parts = []
        if reaction_list:
            snippet_parts.append(f"Reactions: {'; '.join(reaction_list[:3])}")
        if outcome_list:
            snippet_parts.append(f"Outcomes: {'; '.join(outcome_list[:2])}")
        if len(product_names) > 1:
            snippet_parts.append(f"Products: {', '.join(product_names[:3])}")
        snippet = " · ".join(snippet_parts) or "CAERS adverse event report"

        date = rec.get("date_started") or rec.get("date_created") or ""
        if date and len(date) == 8 and date.isdigit():
            date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"

        parsed.append({
            "id": f"caers:{report_id}",
            "title": title[:200],
            "snippet": snippet[:500],
            "url": f"https://open.fda.gov/apis/food/event/{report_id}",
            "source_domain": "fda.gov",
            "date": date or None,
            "relevance": 0.65,
            "why_relevant": f"FDA CAERS food/supplement adverse event for '{query[:40]}'" if query else title[:60],
            "metadata": {
                "report_id": str(report_id),
                "dataset": "food/event",
                "products": product_names[:5],
                "product_roles": product_roles[:5],
                "reactions": reaction_list[:5],
                "outcomes": outcome_list[:3],
                "signal_type": "adverse_event",
            },
        })
    return parsed
