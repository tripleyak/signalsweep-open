"""OpenWeather — global weather data (signalsweep 3.19.0+).

Endpoint: `api.openweathermap.org/data/2.5/weather` for current conditions.
Free tier: 1000 req/day, 60/min. Requires `OPENWEATHER_API_KEY`.

Gated by v3.7 paid-APIs + creds.
"""

from __future__ import annotations

from typing import Any

from . import environmental, paid_api

ENDPOINT = "https://api.openweathermap.org/data/2.5/weather"


def search_openweather(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = cfg.get("OPENWEATHER_API_KEY")
    if not api_key:
        return {"items": None, "error": "credentials_missing"}
    params = {
        "q": topic,
        "appid": api_key,
        "units": cfg.get("OPENWEATHER_UNITS", "imperial"),
    }
    return paid_api.fetch_json(ENDPOINT, params=params)


def parse_openweather_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    data = response["items"]
    if not isinstance(data, dict):
        return []
    location_id = data.get("id")
    location_name = data.get("name") or ""
    if not location_id:
        return []
    coord = data.get("coord") or {}
    main = data.get("main") or {}
    weather_list = data.get("weather") or []
    weather = weather_list[0] if weather_list else {}
    temp = main.get("temp")
    return [
        environmental.build_environmental_item(
            item_id=f"openweather:{location_id}",
            platform="openweather",
            title=f"{location_name} — {weather.get('main') or 'Weather'}",
            snippet=f"{temp}° · {weather.get('description') or ''} · humidity {main.get('humidity', '?')}%".strip(" ·"),
            url=f"https://openweathermap.org/city/{location_id}",
            source_domain="openweathermap.org",
            measurement_type="current_conditions",
            station_id=str(location_id),
            location=location_name,
            latitude=coord.get("lat"),
            longitude=coord.get("lon"),
            unit="°",
            value=temp,
            relevance=0.7,
            why_relevant=f"OpenWeather current conditions for {location_name}",
            extra_metadata={
                "weather_main": weather.get("main", ""),
                "weather_description": weather.get("description", ""),
                "humidity": main.get("humidity"),
                "pressure": main.get("pressure"),
                "wind_speed": (data.get("wind") or {}).get("speed"),
            },
        )
    ]
