"""Amazon Brand Analytics adapter (signalsweep 3.27.0+).

Surfaces Search Query Performance (SQP) and Search Catalog Performance reports
from Amazon Brand Analytics via SP-API Reports API. Reveals impression → click →
cart → purchase funnel leakage per query.

Auth: reuses `sp_api.py` LWA credentials (AMAZON_LWA_* trio).
Requires Brand Registry enrollment for the seller account.

Report types:
  GET_BRAND_ANALYTICS_SEARCH_QUERY_PERFORMANCE_REPORT — query-level funnel
  GET_BRAND_ANALYTICS_SEARCH_CATALOG_PERFORMANCE_REPORT — ASIN-level search perf

Reports are async (request → poll → download CSV). Uses `sp_api_reports.py`
for the lifecycle.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from . import paid_api, sp_api_reports

SQP_REPORT = "GET_BRAND_ANALYTICS_SEARCH_QUERY_PERFORMANCE_REPORT"
SCP_REPORT = "GET_BRAND_ANALYTICS_SEARCH_CATALOG_PERFORMANCE_REPORT"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def _most_recent_week_range() -> tuple[str, str]:
    """Return ISO timestamps for the most recent completed Sun-Sat week."""
    now = datetime.now(timezone.utc)
    days_since_sunday = (now.weekday() + 1) % 7
    last_saturday = now - timedelta(days=days_since_sunday)
    if days_since_sunday == 0:
        last_saturday = now - timedelta(days=7)
    last_saturday = last_saturday.replace(hour=23, minute=59, second=59, microsecond=0)
    last_sunday = last_saturday - timedelta(days=6)
    last_sunday = last_sunday.replace(hour=0, minute=0, second=0, microsecond=0)
    return last_sunday.isoformat(), last_saturday.isoformat()



def search_amazon_brand_analytics(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch Brand Analytics reports. Returns envelope with rows or error."""
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}

    from . import sp_api
    cfg = sp_api._resolve_profile(config)
    refresh = cfg.get("AMAZON_LWA_REFRESH_TOKEN") or ""
    cid = cfg.get("AMAZON_LWA_CLIENT_ID") or ""
    csec = cfg.get("AMAZON_LWA_CLIENT_SECRET") or ""
    if not (refresh and cid and csec):
        return {"items": None, "error": "credentials_missing"}

    start, end = _most_recent_week_range()

    report_options = {"reportPeriod": "WEEK"}

    result = sp_api_reports.fetch_report(
        SQP_REPORT,
        config=config,
        data_start_time=start,
        data_end_time=end,
        report_options=report_options,
        max_poll_attempts=24,
        poll_interval=5,
    )

    if result.get("error"):
        return {"items": result.get("rows"), "error": result["error"]}

    return {"items": result.get("rows") or [], "error": None}


def parse_amazon_brand_analytics_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    """Parse Brand Analytics report rows into normalized item dicts."""
    if response.get("error") or not response.get("items"):
        return []

    rows = response["items"]
    if not isinstance(rows, list):
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    topic_lower = query.lower()

    filtered = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        search_query = (
            row.get("Search Query") or row.get("search_query")
            or row.get("searchQuery") or ""
        ).strip()
        if not search_query:
            continue
        if topic_lower and topic_lower not in search_query.lower():
            continue
        filtered.append((search_query, row))

    def _sort_key(pair: tuple[str, dict]) -> float:
        _, r = pair
        for key in ("Impressions", "impressions", "Search Query Volume", "search_query_volume"):
            val = r.get(key)
            if val is not None:
                try:
                    return -float(str(val).replace(",", ""))
                except ValueError:
                    pass
        return 0.0

    filtered.sort(key=_sort_key)

    parsed = []
    for search_query, row in filtered[:limit]:
        impressions = _safe_int(row, "Impressions", "impressions")
        clicks = _safe_int(row, "Clicks", "clicks")
        cart_adds = _safe_int(row, "Cart Adds", "cart_adds", "cartAdds")
        purchases = _safe_int(row, "Purchases", "purchases")
        click_share = _safe_float(row, "Click Share", "click_share", "clickShare")
        cart_share = _safe_float(row, "Cart Add Share", "cart_add_share", "cartAddShare")
        purchase_share = _safe_float(row, "Purchase Share", "purchase_share", "purchaseShare")

        snippet_parts = []
        if impressions is not None:
            snippet_parts.append(f"Impressions: {impressions:,}")
        if clicks is not None:
            snippet_parts.append(f"Clicks: {clicks:,}")
        if cart_adds is not None:
            snippet_parts.append(f"Cart Adds: {cart_adds:,}")
        if purchases is not None:
            snippet_parts.append(f"Purchases: {purchases:,}")
        snippet = " · ".join(snippet_parts) or f"SQP data for '{search_query}'"

        parsed.append({
            "id": f"sqp:{search_query[:80]}",
            "title": f"SQP: {search_query}",
            "snippet": snippet[:500],
            "url": "https://sellercentral.amazon.com/brand-analytics/search-query-performance",
            "source_domain": "amazon.com",
            "date": None,
            "relevance": 0.8,
            "why_relevant": f"Brand Analytics funnel data for '{query[:40]}'" if query else search_query[:60],
            "metadata": {
                "report_type": "search_query_performance",
                "search_query": search_query,
                "impressions": impressions,
                "clicks": clicks,
                "cart_adds": cart_adds,
                "purchases": purchases,
                "click_share": click_share,
                "cart_share": cart_share,
                "purchase_share": purchase_share,
            },
        })
    return parsed


def _safe_int(row: dict, *keys: str) -> int | None:
    for k in keys:
        val = row.get(k)
        if val is not None:
            try:
                return int(str(val).replace(",", "").strip())
            except (ValueError, TypeError):
                pass
    return None


def _safe_float(row: dict, *keys: str) -> float | None:
    for k in keys:
        val = row.get(k)
        if val is not None:
            try:
                cleaned = str(val).replace(",", "").replace("%", "").strip()
                return float(cleaned)
            except (ValueError, TypeError):
                pass
    return None
