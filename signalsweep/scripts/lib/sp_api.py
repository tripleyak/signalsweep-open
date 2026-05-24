"""Amazon Selling Partner API (SP-API) read-only research adapter (signalsweep 3.7+).

**READ-ONLY.** This module enforces an endpoint allowlist in code. Only catalog
and report-download operations are callable; any non-allowlisted endpoint
raises `NotAllowedEndpoint`. Mutation endpoints (orders, inventory feeds,
pricing updates, campaign changes) are deliberately absent.

Auth: Login-with-Amazon (LWA) refresh-token flow via `amazon_auth.py`.
Modern SP-API (post-2023) does not require AWS sigv4 for the endpoints we use
here — just `x-amz-access-token: <LWA token>`. If future restricted-operation
endpoints require sigv4, add a signing helper alongside the existing flow.

Region routing: `AMAZON_SP_API_REGION` selects the endpoint base URL.
Supported values: `NA` (default), `EU`, `FE`.

Multi-profile support (v3.7 — Unit 7):
- `AMAZON_SP_API_PROFILES` — JSON dict: `{"birdrock": {"AMAZON_SELLER_ID": "A123", "AMAZON_SP_API_REGION": "NA"}, "prospin": {...}}`.
- `AMAZON_SP_API_ACTIVE_PROFILE` — selects profile from the dict.
- When active profile is set, its keys override top-level config for this module.
- Scalar `AMAZON_SELLER_ID` / `AMAZON_SP_API_REGION` still supported as the
  backward-compat single-profile shape.

For research queries (`search_sp_api(query)`), the module hits the Catalog
Items search endpoint and returns normalized SourceItems. No writes, no
order-side calls.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from . import amazon_auth, amazon_marketplaces, paid_api

DEFAULT_REGION = "NA"

# Per-region default marketplace — picks the "biggest" marketplace per cluster
# as the sensible default when AMAZON_SP_API_REGION is set without an explicit
# AMAZON_SP_API_MARKETPLACE_ID. Full region matrix: see
# docs/v3.7-amazon-marketplaces-matrix.md and scripts/lib/amazon_marketplaces.py.
_REGION_DEFAULT_CODES = {"NA": "US", "EU": "UK", "FE": "JP"}

# ALLOWED_ENDPOINTS is the security boundary. These are the only paths this
# module will request against SP-API. Any mutation endpoint is intentionally
# absent. Each entry is a path prefix; URI suffixes like /{asin} are allowed.
ALLOWED_ENDPOINTS: tuple[str, ...] = (
    "/catalog/2022-04-01/items",
    "/reports/2021-06-30/reports",  # read-only report listing + downloads
)

DEPTH_LIMITS = {
    "quick": 5,
    "default": 10,
    "deep": 20,
}


class NotAllowedEndpoint(Exception):
    """Raised when code attempts to call an endpoint not in `ALLOWED_ENDPOINTS`."""


def _is_allowlisted(path: str) -> bool:
    """True iff `path` starts with any entry in `ALLOWED_ENDPOINTS`."""
    return any(path.startswith(prefix) for prefix in ALLOWED_ENDPOINTS)


def _resolve_profile(config: dict[str, Any]) -> dict[str, Any]:
    """Return effective config with active profile overlaid.

    If `AMAZON_SP_API_PROFILES` is a JSON dict and `AMAZON_SP_API_ACTIVE_PROFILE`
    names one of its keys, merge that profile's values over the top-level
    config. Otherwise return config unchanged. Malformed JSON logs a warning
    and returns config unchanged (never raises).
    """
    active = config.get("AMAZON_SP_API_ACTIVE_PROFILE")
    profiles_raw = config.get("AMAZON_SP_API_PROFILES")
    if not (active and profiles_raw):
        return config

    try:
        profiles = json.loads(profiles_raw) if isinstance(profiles_raw, str) else profiles_raw
    except (ValueError, TypeError) as err:
        sys.stderr.write(f"[sp_api] WARNING: AMAZON_SP_API_PROFILES is not valid JSON: {err}\n")
        return config

    if not isinstance(profiles, dict):
        return config

    profile = profiles.get(active)
    if not isinstance(profile, dict):
        sys.stderr.write(
            f"[sp_api] WARNING: AMAZON_SP_API_ACTIVE_PROFILE={active!r} not found in profiles dict; "
            f"available: {list(profiles.keys())}\n"
        )
        return config

    # Dict profile values override top-level config for this call.
    return {**config, **profile}


def _region_base(config: dict[str, Any]) -> str:
    config = _resolve_profile(config)
    region = str(config.get("AMAZON_SP_API_REGION") or DEFAULT_REGION).upper()
    endpoints = amazon_marketplaces.SP_API_ENDPOINTS
    return endpoints.get(region, endpoints[DEFAULT_REGION])


def _marketplace_id(config: dict[str, Any]) -> str:
    config = _resolve_profile(config)
    region = str(config.get("AMAZON_SP_API_REGION") or DEFAULT_REGION).upper()
    code = _REGION_DEFAULT_CODES.get(region, _REGION_DEFAULT_CODES[DEFAULT_REGION])
    marketplace = amazon_marketplaces.get_marketplace(code)
    return marketplace["sp_api_marketplace_id"]


def _call_sp_api(
    path: str,
    *,
    params: dict[str, Any] | None,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Low-level GET against an SP-API endpoint. Enforces allowlist.

    Raises NotAllowedEndpoint if path isn't in ALLOWED_ENDPOINTS (before any
    network call). Otherwise returns paid_api envelope.
    """
    if not _is_allowlisted(path):
        raise NotAllowedEndpoint(
            f"SP-API path not in read-only allowlist: {path}. "
            f"sp_api.py enforces a code-level boundary against mutation operations."
        )

    config = _resolve_profile(config)
    refresh_token = config.get("AMAZON_LWA_REFRESH_TOKEN") or ""
    client_id = config.get("AMAZON_LWA_CLIENT_ID") or ""
    client_secret = config.get("AMAZON_LWA_CLIENT_SECRET") or ""
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
        user_agent_suffix="(sp-api-adapter)",
        cache_key=None,  # no cross-run cache for seller-specific data
    )


def search_sp_api(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search SP-API Catalog Items for products matching topic.

    Returns paid_api envelope. Never raises (except NotAllowedEndpoint if
    invariants are violated — that's a programming bug, not a runtime error).
    """
    config = config or {}
    max_results = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {
        "keywords": topic,
        "marketplaceIds": _marketplace_id(config),
        "pageSize": max_results,
        "includedData": "identifiers,attributes,summaries,productTypes",
    }
    return _call_sp_api("/catalog/2022-04-01/items", params=params, config=config)


def parse_sp_api_response(response: dict[str, Any], query: str = "") -> list[dict[str, Any]]:
    """Parse SP-API Catalog Items search response into normalized item dicts."""
    if response.get("error") or not response.get("items"):
        return []

    body = response["items"]
    if not isinstance(body, dict):
        return []

    items = body.get("items") or []
    if not isinstance(items, list):
        return []

    parsed = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        asin = item.get("asin") or ""
        summaries = item.get("summaries") or []
        summary = summaries[0] if isinstance(summaries, list) and summaries else {}
        title = (summary.get("itemName") or "").strip()
        if not asin or not title:
            continue

        brand = (summary.get("brandName") or "").strip()
        product_type = (summary.get("productType") or "").strip()
        manufacturer = (summary.get("manufacturer") or "").strip()

        identifiers = item.get("identifiers") or []
        upc = ""
        if isinstance(identifiers, list):
            for ident_group in identifiers:
                for ident in ident_group.get("identifiers", []):
                    if ident.get("identifierType") == "UPC":
                        upc = ident.get("identifier", "")
                        break

        snippet_parts = []
        if brand:
            snippet_parts.append(f"Brand: {brand}")
        if manufacturer and manufacturer != brand:
            snippet_parts.append(f"Mfr: {manufacturer}")
        if product_type:
            snippet_parts.append(f"Type: {product_type}")
        snippet = " · ".join(snippet_parts) or f"SP-API catalog entry (ASIN {asin})"

        parsed.append({
            "id": asin,
            "title": title,
            "snippet": snippet,
            "url": f"https://www.amazon.com/dp/{asin}",
            "source_domain": "amazon.com",
            "date": None,
            "relevance": max(0.3, 1.0 - (i * 0.04)),
            "why_relevant": f"SP-API catalog match for '{query}'" if query else "SP-API catalog match",
            "metadata": {
                "asin": asin,
                "brand": brand,
                "manufacturer": manufacturer,
                "product_type": product_type,
                "upc": upc,
            },
        })
    return parsed
