"""Gorgias support ticket adapter (signalsweep 3.28.0+).

Bring-your-own-account source. Surfaces support ticket themes — "revenue that
almost happened." Repeated confusion reveals hidden demand.

Endpoint: https://{domain}.gorgias.com/api/tickets
Auth: GORGIAS_DOMAIN + GORGIAS_EMAIL + GORGIAS_API_KEY (HTTP Basic).
Docs: developers.gorgias.com

Gated by SIGNALSWEEP_DISABLE_PAID_APIS (v3.7 paid-APIs tier).
"""

from __future__ import annotations

import base64
from typing import Any

from . import paid_api

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_gorgias_tickets(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}

    domain = (config.get("GORGIAS_DOMAIN") or "").strip()
    email = (config.get("GORGIAS_EMAIL") or "").strip()
    api_key = (config.get("GORGIAS_API_KEY") or "").strip()
    if not (domain and email and api_key):
        return {"items": None, "error": "credentials_missing"}

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    creds = base64.b64encode(f"{email}:{api_key}".encode()).decode()

    url = f"https://{domain}.gorgias.com/api/tickets"
    params: dict[str, Any] = {"limit": limit, "order_by": "created_datetime:desc"}

    return paid_api.fetch_json(
        url,
        params=params,
        extra_headers={"Authorization": f"Basic {creds}", "Accept": "application/json"},
        cache_key=None,
        user_agent_suffix="(gorgias-tickets-adapter)",
    )


def parse_gorgias_tickets_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    payload = response["items"]
    if isinstance(payload, dict):
        tickets = payload.get("data") or payload.get("tickets") or []
    elif isinstance(payload, list):
        tickets = payload
    else:
        return []

    if not isinstance(tickets, list):
        return []

    topic_lower = query.lower() if query else ""
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    parsed = []

    for i, tkt in enumerate(tickets[:limit]):
        if not isinstance(tkt, dict):
            continue

        tkt_id = tkt.get("id") or ""
        if not tkt_id:
            continue
        tkt_id = str(tkt_id)

        subject = (tkt.get("subject") or "").strip()
        excerpt = (tkt.get("excerpt") or tkt.get("snippet") or "").strip()
        channel = (tkt.get("channel") or "").strip()
        status = (tkt.get("status") or "").strip()
        created = (tkt.get("created_datetime") or "").strip()

        tags = tkt.get("tags") or []
        tag_names = []
        if isinstance(tags, list):
            for t in tags:
                if isinstance(t, dict):
                    tag_names.append(t.get("name") or "")
                elif isinstance(t, str):
                    tag_names.append(t)
            tag_names = [t for t in tag_names if t][:5]

        if topic_lower and subject:
            if topic_lower not in subject.lower() and topic_lower not in excerpt.lower():
                if not any(topic_lower in t.lower() for t in tag_names):
                    continue

        title = subject or f"Gorgias ticket #{tkt_id}"

        snippet_parts = []
        if excerpt:
            snippet_parts.append(excerpt[:300])
        if channel:
            snippet_parts.append(f"Channel: {channel}")
        if status:
            snippet_parts.append(f"Status: {status}")
        if tag_names:
            snippet_parts.append(f"Tags: {', '.join(tag_names[:3])}")
        snippet = " · ".join(snippet_parts) or "Support ticket"

        date = created[:10] if created and len(created) >= 10 else None

        parsed.append({
            "id": f"gorgias:{tkt_id}",
            "title": title[:200],
            "snippet": snippet[:500],
            "url": f"https://app.gorgias.com/tickets/{tkt_id}",
            "source_domain": "gorgias.com",
            "date": date,
            "relevance": max(0.3, 0.75 - (i * 0.02)),
            "why_relevant": f"Support ticket for '{query[:40]}'" if query else title[:60],
            "metadata": {
                "ticket_id": tkt_id,
                "channel": channel,
                "status": status,
                "tags": tag_names,
                "signal_type": "support_ticket",
            },
        })
    return parsed
