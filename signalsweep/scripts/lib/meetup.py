"""Meetup GraphQL API (signalsweep 3.24.0+).

Endpoint: `api.meetup.com/gql`. Requires `MEETUP_ACCESS_TOKEN` (OAuth).
Envelope-first — Meetup's public search APIs are deprecated.

v3.7 paid-APIs + creds.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

ENDPOINT = "https://api.meetup.com/gql"

QUERY = """
query SearchEvents($query: String!, $first: Int!) {
  keywordSearch(filter: {query: $query, source: EVENTS}, input: {first: $first}) {
    edges {
      node {
        result {
          ... on Event {
            id
            title
            description
            eventUrl
            dateTime
            group { name urlname }
          }
        }
      }
    }
  }
}
"""


def search_meetup(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    token = cfg.get("MEETUP_ACCESS_TOKEN")
    if not token:
        return {"items": None, "error": "credentials_missing"}
    return paid_api.post_json(
        ENDPOINT,
        json_body={"query": QUERY, "variables": {"query": topic, "first": 25}},
        extra_headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )


def parse_meetup_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    data = response["items"].get("data") or {}
    ks = data.get("keywordSearch") or {}
    edges = ks.get("edges") or []
    out = []
    for edge in edges:
        node = (edge or {}).get("node") or {}
        event = (node.get("result") or {})
        eid = event.get("id")
        if not eid:
            continue
        group = event.get("group") or {}
        out.append({
            "id": f"meetup:{eid}",
            "title": (event.get("title") or "")[:200],
            "snippet": (event.get("description") or "")[:500],
            "url": event.get("eventUrl") or "",
            "source_domain": "meetup.com",
            "date": (event.get("dateTime") or "")[:10],
            "relevance": 0.7,
            "why_relevant": f"Meetup event — {(event.get('title') or '')[:60]}",
            "metadata": {
                "platform": "meetup",
                "event_id": eid,
                "group_name": group.get("name"),
                "group_urlname": group.get("urlname"),
            },
        })
    return out
