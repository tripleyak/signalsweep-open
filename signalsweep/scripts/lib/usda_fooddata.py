"""USDA FoodData Central nutrition search (signalsweep 3.28.0+).

Nutrition composition data for food/bev gap analysis. Different from
usda_nass (agricultural statistics) and usda_ers (economic research).

Endpoint: https://api.nal.usda.gov/fdc/v1/foods/search
Optional API key via USDA_FOODDATA_API_KEY (free signup at fdc.nal.usda.gov).
Falls back to DEMO_KEY (lower rate limit) when no key provided.

Gated by SIGNALSWEEP_DISABLE_PUBLIC_APIS (v3.6 public-data tier).
"""

from __future__ import annotations

from typing import Any

from . import public_api

SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
DEMO_KEY = "DEMO_KEY"

DEPTH_LIMITS = {"quick": 5, "default": 15, "deep": 30}


def search_usda_fooddata(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not public_api.is_public_apis_enabled(config):
        return {"items": None, "error": "public_apis_disabled"}

    api_key = config.get("USDA_FOODDATA_API_KEY") or DEMO_KEY
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    return public_api.fetch_json(
        SEARCH_URL,
        params={
            "query": topic,
            "pageSize": limit,
            "api_key": api_key,
        },
        cache_key=f"usda_fooddata:{topic}:{depth}",
        user_agent_suffix="(usda-fooddata-adapter)",
    )


def parse_usda_fooddata_response(
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

    foods = payload.get("foods") or []
    if not isinstance(foods, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    parsed = []

    for i, food in enumerate(foods[:limit]):
        if not isinstance(food, dict):
            continue

        fdc_id = food.get("fdcId") or ""
        if not fdc_id:
            continue
        fdc_id = str(fdc_id)

        description = (food.get("description") or "").strip()
        if not description:
            continue

        brand = (food.get("brandOwner") or food.get("brandName") or "").strip()
        data_type = (food.get("dataType") or "").strip()
        category = (food.get("foodCategory") or "").strip()
        ingredients = (food.get("ingredients") or "").strip()
        serving = (food.get("servingSize") or "")
        serving_unit = (food.get("servingSizeUnit") or "").strip()

        nutrients = {}
        for n in (food.get("foodNutrients") or []):
            if not isinstance(n, dict):
                continue
            name = (n.get("nutrientName") or "").strip()
            value = n.get("value")
            unit = (n.get("unitName") or "").strip()
            if name and value is not None:
                nutrients[name] = {"value": value, "unit": unit}

        protein = _get_nutrient(nutrients, "Protein")
        fat = _get_nutrient(nutrients, "Total lipid (fat)")
        carbs = _get_nutrient(nutrients, "Carbohydrate, by difference")
        fiber = _get_nutrient(nutrients, "Fiber, total dietary")
        sugars = _get_nutrient(nutrients, "Sugars, total including NLEA", "Total Sugars")
        energy = _get_nutrient(nutrients, "Energy")
        sodium = _get_nutrient(nutrients, "Sodium, Na")

        snippet_parts = []
        if brand:
            snippet_parts.append(f"Brand: {brand[:60]}")
        if energy is not None:
            snippet_parts.append(f"Energy: {energy} kcal")
        if protein is not None:
            snippet_parts.append(f"Protein: {protein}g")
        if fiber is not None:
            snippet_parts.append(f"Fiber: {fiber}g")
        if sugars is not None:
            snippet_parts.append(f"Sugars: {sugars}g")
        if category:
            snippet_parts.append(f"Category: {category[:40]}")
        snippet = " · ".join(snippet_parts) or f"USDA food: {description}"

        parsed.append({
            "id": f"fdc:{fdc_id}",
            "title": description[:200],
            "snippet": snippet[:500],
            "url": f"https://fdc.nal.usda.gov/fdc-app.html#/food-details/{fdc_id}/nutrients",
            "source_domain": "fdc.nal.usda.gov",
            "date": None,
            "relevance": max(0.3, 0.7 - (i * 0.02)),
            "why_relevant": f"USDA nutrition data for '{query[:40]}'" if query else description[:60],
            "metadata": {
                "fdc_id": fdc_id,
                "brand": brand,
                "data_type": data_type,
                "category": category,
                "energy_kcal": energy,
                "protein_g": protein,
                "fat_g": fat,
                "carbs_g": carbs,
                "fiber_g": fiber,
                "sugars_g": sugars,
                "sodium_mg": sodium,
                "signal_type": "product_attribute",
            },
        })
    return parsed


def _get_nutrient(nutrients: dict, *names: str) -> float | None:
    for name in names:
        entry = nutrients.get(name)
        if entry and entry.get("value") is not None:
            try:
                return float(entry["value"])
            except (ValueError, TypeError):
                pass
    return None
