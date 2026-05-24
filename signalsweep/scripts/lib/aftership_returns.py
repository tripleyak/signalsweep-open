"""AfterShip Returns API adapter (signalsweep 3.28.0+).

Return statuses, reasons, and timing — expectation gap signals.

Endpoint: https://api.aftership.com/returns/v1/returns
Auth: AFTERSHIP_API_KEY (as-api-key header).
Docs: developers.aftership.com

Gated by SIGNALSWEEP_DISABLE_PAID_APIS (v3.7 paid-APIs tier).
"""

from __future__ import annotations

from typing import Any

from . import paid_api

RETURNS_URL = "https://api.aftership.com/returns/v1/returns"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_aftership_returns(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}

    api_key = (config.get("AFTERSHIP_API_KEY") or "").strip()
    if not api_key:
        return {"items": None, "error": "credentials_missing"}

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    return paid_api.fetch_json(
        RETURNS_URL,
        params={"limit": limit},
        extra_headers={"as-api-key": api_key, "Accept": "application/json"},
        cache_key=None,
        user_agent_suffix="(aftership-returns-adapter)",
    )


def parse_aftership_returns_response(
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
        data = payload.get("data") or payload.get("returns") or {}
        if isinstance(data, dict):
            returns = data.get("returns") or data.get("items") or []
        elif isinstance(data, list):
            returns = data
        else:
            returns = []
    elif isinstance(payload, list):
        returns = payload
    else:
        return []
    if not isinstance(returns, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    parsed = []

    for i, ret in enumerate(returns[:limit]):
        if not isinstance(ret, dict):
            continue
        ret_id = ret.get("id") or ret.get("return_id") or ""
        if not ret_id:
            continue
        ret_id = str(ret_id)

        reason = (ret.get("return_reason") or ret.get("reason") or "").strip()
        status = (ret.get("status") or "").strip()
        order_id = (ret.get("order_id") or ret.get("order_number") or "").strip()
        created = (ret.get("created_at") or ret.get("created_time") or "").strip()

        items_list = ret.get("return_line_items") or ret.get("items") or []
        product_names = []
        if isinstance(items_list, list):
            for li in items_list[:5]:
                if isinstance(li, dict):
                    nm = li.get("product_name") or li.get("title") or ""
                    if nm:
                        product_names.append(str(nm).strip()[:80])

        title = reason or f"Return {ret_id}"
        snippet_parts = []
        if reason:
            snippet_parts.append(f"Reason: {reason}")
        if product_names:
            snippet_parts.append(f"Products: {', '.join(product_names[:3])}")
        if status:
            snippet_parts.append(f"Status: {status}")
        snippet = " · ".join(snippet_parts) or "AfterShip return"

        date = created[:10] if created and len(created) >= 10 else None

        parsed.append({
            "id": f"aftership_return:{ret_id}",
            "title": title[:200],
            "snippet": snippet[:500],
            "url": "https://accounts.aftership.com/returns",
            "source_domain": "aftership.com",
            "date": date,
            "relevance": max(0.3, 0.75 - (i * 0.02)),
            "why_relevant": f"Return data for '{query[:40]}'" if query else title[:60],
            "metadata": {
                "return_id": ret_id,
                "reason": reason,
                "status": status,
                "product_names": product_names,
                "signal_type": "return_event",
            },
        })
    return parsed
