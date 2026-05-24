"""Open Food Facts product attribute search (signalsweep 3.28.0+).

Open database of 3M+ food products with ingredients, nutrition, allergens,
labels, and Nutri-Score. For product attribute supply mapping and white-space
analysis — pair with demand signals to find gaps.

Endpoint: https://world.openfoodfacts.org/cgi/search.pl?json=1
No auth required. 500ms polite-sleep.

Gated by SIGNALSWEEP_DISABLE_PUBLIC_APIS (v3.6 public-data tier).
"""

from __future__ import annotations

import time
from typing import Any

from . import public_api

SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"

DEPTH_LIMITS = {"quick": 5, "default": 15, "deep": 30}
POLITE_SLEEP = 0.5


def search_open_food_facts(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not public_api.is_public_apis_enabled(config):
        return {"items": None, "error": "public_apis_disabled"}

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    time.sleep(POLITE_SLEEP)

    return public_api.fetch_json(
        SEARCH_URL,
        params={
            "search_terms": topic,
            "json": "1",
            "page_size": limit,
            "search_simple": "1",
            "action": "process",
        },
        cache_key=f"openfoodfacts:{topic}:{depth}",
        user_agent_suffix="(open-food-facts-adapter)",
    )


def parse_open_food_facts_response(
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

    products = payload.get("products") or []
    if not isinstance(products, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    parsed = []

    for i, prod in enumerate(products[:limit]):
        if not isinstance(prod, dict):
            continue

        code = prod.get("code") or prod.get("_id") or ""
        if not code:
            continue

        name = (prod.get("product_name") or prod.get("product_name_en") or "").strip()
        if not name:
            continue

        brands = (prod.get("brands") or "").strip()
        categories = (prod.get("categories") or "").strip()
        ingredients = (prod.get("ingredients_text") or prod.get("ingredients_text_en") or "").strip()
        nutriscore = (prod.get("nutriscore_grade") or prod.get("nutrition_grades") or "").strip()
        nova = prod.get("nova_group") or ""
        allergens = (prod.get("allergens") or "").strip()
        labels = (prod.get("labels") or "").strip()
        countries = (prod.get("countries") or "").strip()
        quantity = (prod.get("quantity") or "").strip()

        nutriments = prod.get("nutriments") or {}
        energy_kcal = nutriments.get("energy-kcal_100g")
        protein = nutriments.get("proteins_100g")
        fat = nutriments.get("fat_100g")
        carbs = nutriments.get("carbohydrates_100g")
        sugars = nutriments.get("sugars_100g")
        fiber = nutriments.get("fiber_100g")
        sodium = nutriments.get("sodium_100g")

        snippet_parts = []
        if brands:
            snippet_parts.append(f"Brand: {brands[:60]}")
        if nutriscore:
            snippet_parts.append(f"Nutri-Score: {nutriscore.upper()}")
        if nova:
            snippet_parts.append(f"NOVA: {nova}")
        if protein is not None:
            snippet_parts.append(f"Protein: {protein}g/100g")
        if fiber is not None:
            snippet_parts.append(f"Fiber: {fiber}g/100g")
        if sugars is not None:
            snippet_parts.append(f"Sugars: {sugars}g/100g")
        if allergens:
            snippet_parts.append(f"Allergens: {allergens[:80]}")
        snippet = " · ".join(snippet_parts) or f"Food product: {name}"

        url = f"https://world.openfoodfacts.org/product/{code}"

        parsed.append({
            "id": f"off:{code}",
            "title": name[:200],
            "snippet": snippet[:500],
            "url": url,
            "source_domain": "openfoodfacts.org",
            "date": None,
            "relevance": max(0.3, 0.75 - (i * 0.02)),
            "why_relevant": f"Food product attribute data for '{query[:40]}'" if query else name[:60],
            "metadata": {
                "barcode": code,
                "brands": brands,
                "categories": categories[:200],
                "nutriscore_grade": nutriscore,
                "nova_group": str(nova) if nova else "",
                "allergens": allergens[:200],
                "labels": labels[:200],
                "quantity": quantity,
                "energy_kcal_100g": energy_kcal,
                "protein_100g": protein,
                "fat_100g": fat,
                "carbs_100g": carbs,
                "sugars_100g": sugars,
                "fiber_100g": fiber,
                "sodium_100g": sodium,
                "signal_type": "product_attribute",
            },
        })
    return parsed
