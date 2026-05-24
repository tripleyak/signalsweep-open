"""Eventbrite v3 event search (signalsweep 3.24.0+).

Endpoint: `eventbriteapi.com/v3/events/search/`. Requires `EVENTBRITE_TOKEN`.

NOTE: As of 2020, Eventbrite deprecated public event search for most accounts;
the endpoint may return empty results or require an organization-owned scope.
We ship envelope-first and document this limitation.

v3.7 paid-APIs + creds.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

ENDPOINT = "https://www.eventbriteapi.com/v3/events/search/"


def search_eventbrite(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    token = cfg.get("EVENTBRITE_TOKEN")
    if not token:
        return {"items": None, "error": "credentials_missing"}
    params = {"q": topic, "expand": "venue,organizer"}
    if from_date:
        params["start_date.range_start"] = f"{from_date}T00:00:00"
    if to_date:
        params["start_date.range_end"] = f"{to_date}T23:59:59"
    return paid_api.fetch_json(ENDPOINT, params=params, extra_headers={"Authorization": f"Bearer {token}"})


def parse_eventbrite_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    events = response["items"].get("events") or []
    out = []
    for e in events:
        eid = e.get("id")
        if not eid:
            continue
        out.append({
            "id": f"eventbrite:{eid}",
            "title": ((e.get("name") or {}).get("text") or "")[:200],
            "snippet": ((e.get("description") or {}).get("text") or "")[:500],
            "url": e.get("url") or "",
            "source_domain": "eventbrite.com",
            "date": (e.get("start") or {}).get("local", "")[:10],
            "relevance": 0.7,
            "why_relevant": f"Eventbrite event — {(e.get('name') or {}).get('text', '')[:60]}",
            "metadata": {
                "platform": "eventbrite",
                "event_id": eid,
                "venue": ((e.get("venue") or {}).get("name")),
                "organizer": ((e.get("organizer") or {}).get("name")),
                "is_free": e.get("is_free"),
                "online_event": e.get("online_event"),
            },
        })
    return out
