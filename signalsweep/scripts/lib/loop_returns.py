"""Loop Returns API adapter (signalsweep 3.28.0+).

Bring-your-own-account. Return reasons and return events — demand mismatch
and product failure mode signals.

Endpoint: https://api.loopreturns.com/api/v1/returns
Auth: LOOP_RETURNS_API_KEY (Bearer).
Docs: docs.loopreturns.com

Gated by SIGNALSWEEP_DISABLE_PAID_APIS (v3.7 paid-APIs tier).
"""

from __future__ import annotations

from typing import Any

from . import paid_api

RETURNS_URL = "https://api.loopreturns.com/api/v1/returns"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_loop_returns(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}

    api_key = (config.get("LOOP_RETURNS_API_KEY") or "").strip()
    if not api_key:
        return {"items": None, "error": "credentials_missing"}

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    return paid_api.fetch_json(
        RETURNS_URL,
        auth=paid_api.AuthSpec(type="bearer", value=api_key),
        params={"per_page": limit},
        cache_key=None,
        user_agent_suffix="(loop-returns-adapter)",
    )


def parse_loop_returns_response(
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
        returns = payload.get("data") or payload.get("returns") or []
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
        ret_id = ret.get("id") or ""
        if not ret_id:
            continue
        ret_id = str(ret_id)

        reason = (ret.get("return_reason") or ret.get("reason") or "").strip()
        status = (ret.get("state") or ret.get("status") or "").strip()
        order_name = (ret.get("order_name") or "").strip()
        created = (ret.get("created_at") or "").strip()

        line_items = ret.get("line_items") or ret.get("return_line_items") or []
        product_names = []
        if isinstance(line_items, list):
            for li in line_items[:5]:
                if isinstance(li, dict):
                    nm = li.get("title") or li.get("product_title") or ""
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
        snippet = " · ".join(snippet_parts) or "Loop return"

        date = created[:10] if created and len(created) >= 10 else None

        parsed.append({
            "id": f"loop_return:{ret_id}",
            "title": title[:200],
            "snippet": snippet[:500],
            "url": "https://app.loopreturns.com/",
            "source_domain": "loopreturns.com",
            "date": date,
            "relevance": max(0.3, 0.75 - (i * 0.02)),
            "why_relevant": f"Return reason for '{query[:40]}'" if query else title[:60],
            "metadata": {
                "return_id": ret_id,
                "reason": reason,
                "status": status,
                "product_names": product_names,
                "signal_type": "return_event",
            },
        })
    return parsed
