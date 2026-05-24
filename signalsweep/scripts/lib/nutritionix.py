"""Nutritionix branded food search (signalsweep 3.28.0+).

1M+ branded grocery/restaurant food items. Complements Open Food Facts with
US-market branded data and restaurant items.

Endpoint: https://trackapi.nutritionix.com/v2/search/instant
Auth: NUTRITIONIX_APP_ID + NUTRITIONIX_API_KEY (x-app-id + x-app-key headers).

Gated by SIGNALSWEEP_DISABLE_PAID_APIS (v3.7 paid-APIs tier).
"""

from __future__ import annotations
from typing import Any
from . import paid_api

SEARCH_URL = "https://trackapi.nutritionix.com/v2/search/instant"
DEPTH_LIMITS = {"quick": 5, "default": 15, "deep": 30}


def search_nutritionix(topic: str, from_date: str, to_date: str, depth: str = "default", config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}
    app_id = (config.get("NUTRITIONIX_APP_ID") or "").strip()
    api_key = (config.get("NUTRITIONIX_API_KEY") or "").strip()
    if not (app_id and api_key):
        return {"items": None, "error": "credentials_missing"}
    return paid_api.fetch_json(
        SEARCH_URL,
        params={"query": topic, "branded": "true", "detailed": "true"},
        extra_headers={"x-app-id": app_id, "x-app-key": api_key},
        cache_key=f"nutritionix:{topic}:{depth}",
        user_agent_suffix="(nutritionix-adapter)",
    )


def parse_nutritionix_response(response: dict[str, Any], query: str = "", from_date: str = "", to_date: str = "", depth: str = "default") -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    payload = response["items"]
    if not isinstance(payload, dict):
        return []
    branded = payload.get("branded") or []
    if not isinstance(branded, list):
        return []
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    parsed = []
    for i, item in enumerate(branded[:limit]):
        if not isinstance(item, dict):
            continue
        nix_id = item.get("nix_item_id") or item.get("nix_brand_id") or ""
        if not nix_id:
            continue
        name = (item.get("food_name") or item.get("brand_name_item_name") or "").strip()
        if not name:
            continue
        brand = (item.get("brand_name") or "").strip()
        calories = item.get("nf_calories")
        protein = item.get("nf_protein")
        serving = item.get("serving_qty")
        serving_unit = (item.get("serving_unit") or "").strip()
        snippet_parts = []
        if brand:
            snippet_parts.append(f"Brand: {brand}")
        if calories is not None:
            snippet_parts.append(f"Cal: {calories}")
        if protein is not None:
            snippet_parts.append(f"Protein: {protein}g")
        if serving and serving_unit:
            snippet_parts.append(f"Serving: {serving} {serving_unit}")
        snippet = " · ".join(snippet_parts) or f"Nutritionix: {name}"
        parsed.append({
            "id": f"nutritionix:{nix_id}",
            "title": name[:200],
            "snippet": snippet[:500],
            "url": f"https://www.nutritionix.com/food/{name.replace(' ', '-').lower()}",
            "source_domain": "nutritionix.com",
            "date": None,
            "relevance": max(0.3, 0.7 - (i * 0.02)),
            "why_relevant": f"Nutritionix data for '{query[:40]}'" if query else name[:60],
            "metadata": {"nix_id": str(nix_id), "brand": brand, "calories": calories, "protein_g": protein, "signal_type": "product_attribute"},
        })
    return parsed
