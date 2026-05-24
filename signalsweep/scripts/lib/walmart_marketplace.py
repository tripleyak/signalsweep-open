"""Walmart Marketplace API — read-only seller research (signalsweep 3.14.0+).

**READ-ONLY.** Seller catalog + performance snapshots only. Mutation endpoints
(feeds, inventory updates, price updates) are deliberately absent.

Auth: OAuth 2.0 client-credentials flow via `marketplace_oauth.py`. Requires:
  `WALMART_MARKETPLACE_CLIENT_ID`
  `WALMART_MARKETPLACE_CLIENT_SECRET`

Walmart Marketplace is approved-seller-only. Ships with `credentials_missing`
envelope; activates when approved-seller account lands.

v3.27.0 enhancements:
  - Insights API: listing quality scores, unpublished items
  - Depth-gated: insights only at default/deep depth

Docs: developer.walmart.com/doc/us/mp/
"""

from __future__ import annotations

from typing import Any

from . import marketplace_oauth


TOKEN_URL = "https://marketplace.walmartapis.com/v3/token"
BASE_URL = "https://marketplace.walmartapis.com"

# Read-only allowlist. Mutation endpoints (feeds, inventory, price) absent.
ALLOWED_ENDPOINTS: tuple[str, ...] = (
    "/v3/items",              # items catalog
    "/v3/inventory",          # inventory GET (read-only)
    "/v3/insights",           # seller performance insights
    "/v3/reports",            # reports download
)

DEPTH_LIMITS = {"quick": 5, "default": 10, "deep": 25}
INSIGHTS_DEPTH_GATE = {"default", "deep"}


class NotAllowedEndpoint(Exception):
    pass


def _is_allowlisted(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in ALLOWED_ENDPOINTS)


def search_walmart_marketplace(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    client_id = config.get("WALMART_MARKETPLACE_CLIENT_ID") or ""
    client_secret = config.get("WALMART_MARKETPLACE_CLIENT_SECRET") or ""
    if not (client_id and client_secret):
        return {"items": None, "error": "credentials_missing"}

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    path = "/v3/items"

    if not _is_allowlisted(path):
        raise NotAllowedEndpoint(f"Walmart path not in read-only allowlist: {path}")

    params = {"query": topic, "limit": limit}

    catalog_result = marketplace_oauth.fetch_with_bearer(
        f"{BASE_URL}{path}",
        vendor="walmart_marketplace",
        token_url=TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret,
        grant_type="client_credentials",
        params=params,
        cache_key=None,
        user_agent_suffix="(walmart-marketplace-adapter)",
    )

    if depth not in INSIGHTS_DEPTH_GATE:
        return catalog_result

    insights = _fetch_insights(topic, config)
    if catalog_result.get("error"):
        return catalog_result

    body = catalog_result.get("items") or {}
    if not isinstance(body, dict):
        body = {}
    body["_insights"] = insights
    return {"items": body, "error": None}


def parse_walmart_marketplace_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    body = response["items"]
    if not isinstance(body, dict):
        return []

    items = body.get("ItemResponse") or body.get("items") or body.get("data") or []
    if not isinstance(items, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for i, item in enumerate(items[:limit]):
        if not isinstance(item, dict):
            continue
        item_id = item.get("sku") or item.get("wpid") or item.get("itemId") or ""
        title = (item.get("productName") or item.get("title") or "").strip()
        if not item_id or not title:
            continue

        brand = (item.get("brand") or "").strip()
        price = 0.0
        price_obj = item.get("price") or {}
        if isinstance(price_obj, dict):
            try:
                price = float(price_obj.get("amount", 0) or 0)
            except (TypeError, ValueError):
                price = 0.0
        elif isinstance(price_obj, (int, float)):
            price = float(price_obj)

        meta: dict[str, Any] = {
            "sku": item_id,
            "brand": brand,
            "price": price,
            "marketplace": "walmart_us",
        }

        insights_data = body.get("_insights") or {} if isinstance(body, dict) else {}
        quality_map = insights_data.get("quality") or {}
        if item_id in quality_map:
            qs = quality_map[item_id]
            meta["listing_quality_score"] = qs.get("score")
            meta["listing_quality_issues"] = qs.get("issues", [])

        unpub_map = insights_data.get("unpublished") or {}
        if item_id in unpub_map:
            meta["unpublished_reason"] = unpub_map[item_id]

        snippet_parts = [f"Walmart Marketplace — brand: {brand or 'n/a'}, price: ${price:.2f}"]
        if meta.get("listing_quality_score") is not None:
            snippet_parts.append(f"quality: {meta['listing_quality_score']}")

        parsed.append({
            "id": f"walmart_mp:{item_id}",
            "title": title[:200],
            "snippet": " · ".join(snippet_parts),
            "url": f"https://www.walmart.com/ip/{item_id}",
            "source_domain": "walmart.com",
            "date": to_date or None,
            "relevance": max(0.3, 0.75 - (i * 0.02)),
            "why_relevant": f"Walmart Marketplace match for '{query[:40]}'" if query else title[:60],
            "metadata": meta,
        })
    return parsed


def _fetch_insights(
    topic: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Fetch listing quality insights. Returns dict with quality/unpublished maps.

    Never raises. Returns empty dict on any failure (insights are additive,
    not required for core catalog results).
    """
    client_id = config.get("WALMART_MARKETPLACE_CLIENT_ID") or ""
    client_secret = config.get("WALMART_MARKETPLACE_CLIENT_SECRET") or ""
    if not (client_id and client_secret):
        return {}

    path = "/v3/insights/items/listingQuality/score"
    if not _is_allowlisted("/v3/insights"):
        return {}

    result = marketplace_oauth.fetch_with_bearer(
        f"{BASE_URL}{path}",
        vendor="walmart_marketplace",
        token_url=TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret,
        grant_type="client_credentials",
        params={"limit": 50},
        cache_key=None,
        user_agent_suffix="(walmart-marketplace-insights)",
    )

    if result.get("error") or not result.get("items"):
        return {}

    payload = result["items"]
    if not isinstance(payload, dict):
        return {}

    quality_map: dict[str, dict[str, Any]] = {}
    quality_items = payload.get("payload") or payload.get("items") or payload.get("data") or []
    if isinstance(quality_items, list):
        for qi in quality_items:
            if not isinstance(qi, dict):
                continue
            sku = qi.get("sku") or qi.get("itemId") or ""
            if not sku:
                continue
            score = qi.get("score") or qi.get("listingQualityScore")
            issues = qi.get("issues") or qi.get("qualityIssues") or []
            if isinstance(issues, list):
                issues = [str(iss) if not isinstance(iss, str) else iss for iss in issues[:5]]
            quality_map[str(sku)] = {"score": score, "issues": issues}

    unpub_map: dict[str, str] = {}
    unpub_items = payload.get("unpublishedItems") or []
    if isinstance(unpub_items, list):
        for ui in unpub_items:
            if not isinstance(ui, dict):
                continue
            sku = ui.get("sku") or ui.get("itemId") or ""
            reason = ui.get("reason") or ui.get("unpublishedReason") or "unknown"
            if sku:
                unpub_map[str(sku)] = str(reason)

    return {"quality": quality_map, "unpublished": unpub_map}
