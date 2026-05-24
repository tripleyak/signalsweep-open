"""TikTok Shop Partner API — seller-side read-only research (signalsweep 3.14.0+).

Distinct from v3.7's `tiktok_shop` adapter (consumer-side ScrapeCreators
backend). This adapter hits TikTok's official Partner API for authenticated
seller queries (shop catalog, product listings, seller-facing metrics).

**READ-ONLY.** Order actions, SKU updates, fulfillment operations absent.

Auth: TikTok Shop Partner OAuth 2.0. Partner-app registration required
(slow approval process). Requires:
  `TIKTOK_SHOP_PARTNER_APP_KEY`
  `TIKTOK_SHOP_PARTNER_APP_SECRET`
  `TIKTOK_SHOP_PARTNER_ACCESS_TOKEN` (long-lived; obtained via consent flow)

Envelope-first: any missing credential → `credentials_missing`.

Docs: partner.tiktokshop.com/doc
"""

from __future__ import annotations

from typing import Any

from . import paid_api


BASE_URL = "https://open-api.tiktokglobalshop.com"

ALLOWED_ENDPOINTS: tuple[str, ...] = (
    "/product/202309/products/search",
    "/seller/202309/shops",               # shop info GET (no update suffix)
    "/listing/202309/listings/search",    # listing search
)

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


class NotAllowedEndpoint(Exception):
    pass


def _is_allowlisted(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in ALLOWED_ENDPOINTS)


def search_tiktok_shop_seller(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    app_key = config.get("TIKTOK_SHOP_PARTNER_APP_KEY") or ""
    app_secret = config.get("TIKTOK_SHOP_PARTNER_APP_SECRET") or ""
    access_token = config.get("TIKTOK_SHOP_PARTNER_ACCESS_TOKEN") or ""
    if not (app_key and app_secret and access_token):
        return {"items": None, "error": "credentials_missing"}

    path = "/product/202309/products/search"
    if not _is_allowlisted(path):
        raise NotAllowedEndpoint(f"TikTok Shop path not in read-only allowlist: {path}")

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {
        "keyword": topic,
        "page_size": limit,
        "app_key": app_key,
    }

    return paid_api.fetch_json(
        f"{BASE_URL}{path}",
        params=params,
        extra_headers={"x-tts-access-token": access_token},
        user_agent_suffix="(tiktok-shop-seller-adapter)",
        cache_key=None,
    )


def parse_tiktok_shop_seller_response(
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

    data = body.get("data") or {}
    if not isinstance(data, dict):
        return []

    products = data.get("products") or data.get("items") or []
    if not isinstance(products, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for i, product in enumerate(products[:limit]):
        if not isinstance(product, dict):
            continue
        product_id = product.get("id") or product.get("product_id") or ""
        title = (product.get("title") or product.get("name") or "").strip()
        if not product_id or not title:
            continue

        brand = (product.get("brand", {}) or {}).get("name", "") if isinstance(product.get("brand"), dict) else ""
        price_obj = product.get("price", {}) or {}
        price = 0.0
        if isinstance(price_obj, dict):
            try:
                price = float(price_obj.get("sale_price") or price_obj.get("original_price") or 0)
            except (TypeError, ValueError):
                price = 0.0
        status = product.get("status") or ""

        parsed.append({
            "id": f"tiktok_shop_seller:{product_id}",
            "title": title[:200],
            "snippet": f"TikTok Shop seller product — brand: {brand or 'n/a'}, price: ${price:.2f}, status: {status}",
            "url": f"https://shop.tiktok.com/view/product/{product_id}",
            "source_domain": "shop.tiktok.com",
            "date": to_date or None,
            "relevance": max(0.3, 0.7 - (i * 0.02)),
            "why_relevant": f"TikTok Shop seller match for '{query[:40]}'" if query else title[:60],
            "metadata": {
                "product_id": product_id,
                "brand": brand,
                "price": price,
                "status": status,
                "business_side": "seller_partner",
            },
        })
    return parsed
