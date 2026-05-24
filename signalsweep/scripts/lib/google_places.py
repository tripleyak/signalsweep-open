"""Google Places API (New) text search (signalsweep 3.24.0+).

Endpoint: `places.googleapis.com/v1/places:searchText`. POST with
X-Goog-Api-Key header + X-Goog-FieldMask.

Requires `GOOGLE_PLACES_API_KEY`. v3.7 paid-APIs + creds.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
DEFAULT_FIELD_MASK = "places.id,places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.location,places.types,places.primaryType"


def search_google_places(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = cfg.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        return {"items": None, "error": "credentials_missing"}
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": cfg.get("GOOGLE_PLACES_FIELD_MASK", DEFAULT_FIELD_MASK),
        "Content-Type": "application/json",
    }
    return paid_api.post_json(
        ENDPOINT,
        json_body={"textQuery": topic},
        extra_headers=headers,
    )


def parse_google_places_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    places = response["items"].get("places") or []
    out = []
    for p in places:
        pid = p.get("id")
        if not pid:
            continue
        display_name = (p.get("displayName") or {}).get("text") or pid
        location = p.get("location") or {}
        out.append({
            "id": f"google_places:{pid}",
            "title": f"{display_name} — {(p.get('formattedAddress') or '')[:80]}",
            "snippet": f"{p.get('rating', '?')}★ ({p.get('userRatingCount', 0)} reviews) · {p.get('primaryType', '')}",
            "url": f"https://www.google.com/maps/place/?q=place_id:{pid}",
            "source_domain": "google.com",
            "date": None,
            "relevance": 0.7,
            "why_relevant": f"Google Places — {display_name}",
            "metadata": {
                "platform": "google_places",
                "place_id": pid,
                "rating": p.get("rating"),
                "rating_count": p.get("userRatingCount"),
                "address": p.get("formattedAddress"),
                "latitude": location.get("latitude"),
                "longitude": location.get("longitude"),
                "types": p.get("types") or [],
                "primary_type": p.get("primaryType"),
            },
        })
    return out
