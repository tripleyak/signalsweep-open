"""Amazon Vendor Central API (1P wholesale) — read-only research adapter (signalsweep 3.14.0+).

**READ-ONLY.** Parallels `sp_api.py` in shape (LWA + allowlist) but covers the
distinct 1P vendor business relationship (wholesale purchase orders, vendor
catalog, retail analytics) rather than 3P marketplace.

Why separate from `sp_api.py`:
- Different app registration in Amazon's Vendor Portal (vs Seller Central).
- Different OAuth scopes (`vendor::*` instead of `sellingpartnerapi::*`).
- Distinct endpoint set (`vendor/*` paths vs `catalog/*` + `reports/*`).
- Different business semantics — 1P (Amazon buys from you) vs 3P (you sell
  through Amazon). Separation of concerns matters for audit.

Auth: LWA refresh-token flow via `amazon_auth.py` (same module — LWA token
shape is identical). Separate env-var trio:
  `AMAZON_VENDOR_LWA_REFRESH_TOKEN`
  `AMAZON_VENDOR_LWA_CLIENT_ID`
  `AMAZON_VENDOR_LWA_CLIENT_SECRET`

Region routing: `AMAZON_VENDOR_REGION` (`NA` | `EU` | `FE`, default `NA`).

Docs: developer-docs.amazon.com/sp-api/docs/vendor-apis
"""

from __future__ import annotations

from typing import Any

from . import amazon_auth, amazon_marketplaces, paid_api


DEFAULT_REGION = "NA"

# Read-only allowlist. Mutation endpoints (create PO, update shipment,
# acknowledge order) are deliberately absent.
ALLOWED_ENDPOINTS: tuple[str, ...] = (
    "/vendor/catalog/",            # vendor catalog items lookup
    "/vendor/orders/v1/purchaseOrders",   # PO listing (GET only)
    "/vendor/shipments/v1/shipments",     # shipment listing (GET only)
)

DEPTH_LIMITS = {"quick": 5, "default": 10, "deep": 20}


class NotAllowedEndpoint(Exception):
    """Raised when code attempts an endpoint not in `ALLOWED_ENDPOINTS`."""


def _is_allowlisted(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in ALLOWED_ENDPOINTS)


def _region_base(config: dict[str, Any]) -> str:
    region = str(config.get("AMAZON_VENDOR_REGION") or DEFAULT_REGION).upper()
    endpoints = amazon_marketplaces.SP_API_ENDPOINTS
    return endpoints.get(region, endpoints[DEFAULT_REGION])


def _call_vendor_api(
    path: str,
    *,
    params: dict[str, Any] | None,
    config: dict[str, Any],
) -> dict[str, Any]:
    if not _is_allowlisted(path):
        raise NotAllowedEndpoint(
            f"Vendor API path not in read-only allowlist: {path}. "
            f"amazon_vendor.py enforces a code-level boundary against mutation operations."
        )

    refresh_token = config.get("AMAZON_VENDOR_LWA_REFRESH_TOKEN") or ""
    client_id = config.get("AMAZON_VENDOR_LWA_CLIENT_ID") or ""
    client_secret = config.get("AMAZON_VENDOR_LWA_CLIENT_SECRET") or ""
    if not (refresh_token and client_id and client_secret):
        return {"items": None, "error": "credentials_missing"}

    access_token, _ = amazon_auth.get_lwa_access_token(refresh_token, client_id, client_secret)
    if not access_token:
        reason = amazon_auth.get_last_error() or "lwa_token_failed"
        return {"items": None, "error": reason}

    base = _region_base(config)
    url = f"{base}{path}"
    return paid_api.fetch_json(
        url,
        params=params,
        extra_headers={"x-amz-access-token": access_token},
        user_agent_suffix="(amazon-vendor-adapter)",
        cache_key=None,
    )


def search_amazon_vendor(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search vendor catalog for ASINs matching topic."""
    config = config or {}
    max_results = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {
        "keywords": topic,
        "pageSize": max_results,
    }
    return _call_vendor_api("/vendor/catalog/2020-12-01/items", params=params, config=config)


def parse_amazon_vendor_response(
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

    items = body.get("items") or body.get("results") or []
    if not isinstance(items, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for i, item in enumerate(items[:limit]):
        if not isinstance(item, dict):
            continue
        asin = item.get("asin") or item.get("vendorProductIdentifier") or ""
        title = (item.get("title") or item.get("itemName") or "").strip()
        if not asin or not title:
            continue

        brand = (item.get("brand") or item.get("brandName") or "").strip()
        category = (item.get("category") or item.get("productCategory") or "").strip()

        snippet_parts = []
        if brand:
            snippet_parts.append(f"Brand: {brand}")
        if category:
            snippet_parts.append(f"Category: {category}")
        snippet = " · ".join(snippet_parts) or f"Vendor catalog entry (ASIN {asin})"

        parsed.append({
            "id": f"vendor:{asin}",
            "title": title[:200],
            "snippet": snippet[:500],
            "url": f"https://www.amazon.com/dp/{asin}",
            "source_domain": "amazon.com",
            "date": to_date or None,
            "relevance": max(0.3, 0.8 - (i * 0.02)),
            "why_relevant": f"Vendor Central catalog match for '{query[:40]}'" if query else title[:60],
            "metadata": {
                "asin": asin,
                "brand": brand,
                "category": category,
                "business_relationship": "1P_vendor",
            },
        })
    return parsed
