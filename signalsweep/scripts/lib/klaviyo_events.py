"""Klaviyo Events API adapter (signalsweep 3.28.0+).

Bring-your-own-account source. Surfaces customer behavioral events, lifecycle
metrics, and retention signals from a Klaviyo account. Reveals almost-purchases,
habit formation, and demand friction.

Endpoint: https://a.]klaviyo.com/api/events/
Auth: KLAVIYO_API_KEY (private API key with events:read scope).
Docs: developers.klaviyo.com/en/reference/get_events

Gated by SIGNALSWEEP_DISABLE_PAID_APIS (v3.7 paid-APIs tier).
Envelope-first: returns credentials_missing when key absent.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

EVENTS_URL = "https://a.klaviyo.com/api/events/"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_klaviyo_events(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}

    api_key = (config.get("KLAVIYO_API_KEY") or "").strip()
    if not api_key:
        return {"items": None, "error": "credentials_missing"}

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    params: dict[str, Any] = {
        "page[size]": min(limit, 50),
        "sort": "-datetime",
    }

    if topic:
        params["filter"] = f"contains(metric.name,'{topic}')"

    return paid_api.fetch_json(
        EVENTS_URL,
        auth=paid_api.AuthSpec(type="header", name="Authorization", value=f"Klaviyo-API-Key {api_key}"),
        params=params,
        extra_headers={
            "Accept": "application/json",
            "revision": "2024-10-15",
        },
        cache_key=None,
        user_agent_suffix="(klaviyo-events-adapter)",
    )


def parse_klaviyo_events_response(
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

    events = payload.get("data") or []
    if not isinstance(events, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    parsed = []

    for i, evt in enumerate(events[:limit]):
        if not isinstance(evt, dict):
            continue

        evt_id = evt.get("id") or ""
        if not evt_id:
            continue

        attrs = evt.get("attributes") or {}
        metric_id = attrs.get("metric_id") or ""
        event_props = attrs.get("event_properties") or {}
        datetime_str = attrs.get("datetime") or ""
        timestamp = attrs.get("timestamp") or ""

        metric_name = ""
        metric_rel = (evt.get("relationships") or {}).get("metric", {})
        if isinstance(metric_rel, dict):
            metric_data = metric_rel.get("data") or {}
            if isinstance(metric_data, dict):
                metric_name = metric_data.get("id") or ""

        profile_rel = (evt.get("relationships") or {}).get("profile", {})
        profile_id = ""
        if isinstance(profile_rel, dict):
            pd = profile_rel.get("data") or {}
            if isinstance(pd, dict):
                profile_id = pd.get("id") or ""

        value = event_props.get("$value") or event_props.get("value") or ""
        item_names = event_props.get("ItemNames") or event_props.get("item_names") or []
        if isinstance(item_names, list):
            item_names = [str(n) for n in item_names[:5]]

        title = metric_name or f"Klaviyo event {evt_id[:12]}"

        snippet_parts = []
        if item_names:
            snippet_parts.append(f"Items: {', '.join(item_names[:3])}")
        if value:
            snippet_parts.append(f"Value: ${value}" if str(value).replace(".", "").isdigit() else f"Value: {value}")
        if datetime_str:
            snippet_parts.append(f"At: {datetime_str[:19]}")
        snippet = " · ".join(snippet_parts) or "Klaviyo behavioral event"

        date = datetime_str[:10] if datetime_str and len(datetime_str) >= 10 else None

        parsed.append({
            "id": f"klaviyo:{evt_id[:20]}",
            "title": title[:200],
            "snippet": snippet[:500],
            "url": "https://www.klaviyo.com/analytics/events",
            "source_domain": "klaviyo.com",
            "date": date,
            "relevance": max(0.3, 0.75 - (i * 0.02)),
            "why_relevant": f"Klaviyo event for '{query[:40]}'" if query else title[:60],
            "metadata": {
                "event_id": evt_id,
                "metric_name": metric_name,
                "item_names": item_names,
                "value": str(value) if value else "",
                "profile_id": profile_id,
                "signal_type": "customer_event",
            },
        })
    return parsed
