"""Shopify Admin API analytics adapter (signalsweep 3.27.0+).

First "bring your own store" source. Uses shopifyqlQuery GraphQL endpoint
for store-level cohort economics, AOV patterns, and SKU productivity.

Auth: `SHOPIFY_STORE` (store subdomain) + `SHOPIFY_ACCESS_TOKEN` (Admin API
access token with read_reports, read_orders, read_products scopes).

Gated by SIGNALSWEEP_DISABLE_PAID_APIS + credential presence.
Envelope-first: returns credentials_missing when tokens absent.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from . import paid_api

API_VERSION = "2026-01"
DEPTH_LIMITS = {"quick": 1, "default": 3, "deep": 5}

SHOPIFY_QUERIES = [
    {
        "name": "top_products",
        "label": "Top Products (30d)",
        "query": "FROM sales SHOW total_sales, total_orders BY product_title SINCE -30d ORDER BY total_sales DESC",
    },
    {
        "name": "aov_trend",
        "label": "AOV Trend (30d)",
        "query": "FROM orders SHOW average_order_value BY day SINCE -30d ORDER BY day ASC",
    },
    {
        "name": "product_performance",
        "label": "Product Performance",
        "query": "FROM products SHOW total_sales, total_orders BY product_title ORDER BY total_orders DESC",
    },
    {
        "name": "sales_by_channel",
        "label": "Sales by Channel (30d)",
        "query": "FROM sales SHOW total_sales BY channel_title SINCE -30d ORDER BY total_sales DESC",
    },
    {
        "name": "refund_rate",
        "label": "Refund Rate (30d)",
        "query": "FROM sales SHOW total_sales, returns BY product_title SINCE -30d ORDER BY returns DESC",
    },
]


def _graphql_url(store: str) -> str:
    store = store.strip().replace(".myshopify.com", "")
    return f"https://{store}.myshopify.com/admin/api/{API_VERSION}/graphql.json"


def search_shopify_analytics(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run ShopifyQL analytics queries. Returns envelope with query results."""
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}

    store = (config.get("SHOPIFY_STORE") or "").strip()
    token = (config.get("SHOPIFY_ACCESS_TOKEN") or "").strip()
    if not (store and token):
        return {"items": None, "error": "credentials_missing"}

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    queries_to_run = SHOPIFY_QUERIES[:limit]
    url = _graphql_url(store)

    results = []
    for sq in queries_to_run:
        gql = {
            "query": """
                query shopifyqlQuery($query: String!) {
                    shopifyqlQuery(query: $query) {
                        __typename
                        ... on TableResponse {
                            tableData {
                                rowData
                                columns { name dataType }
                            }
                        }
                        ... on PolarisVizResponse {
                            data { key data { key value } }
                        }
                    }
                }
            """,
            "variables": {"query": sq["query"]},
        }

        resp = paid_api.post_json(
            url,
            gql,
            extra_headers={
                "X-Shopify-Access-Token": token,
                "Content-Type": "application/json",
            },
            user_agent_suffix="(shopify-analytics-adapter)",
            timeout=20,
        )

        if resp.get("error"):
            results.append({
                "query_name": sq["name"],
                "label": sq["label"],
                "error": resp["error"],
                "data": None,
            })
            continue

        payload = resp.get("items") or {}
        results.append({
            "query_name": sq["name"],
            "label": sq["label"],
            "error": None,
            "data": payload,
        })

    return {"items": results, "error": None}


def parse_shopify_analytics_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    """Parse Shopify analytics results into normalized item dicts."""
    if response.get("error") or not response.get("items"):
        return []

    results = response["items"]
    if not isinstance(results, list):
        return []

    store = ""
    parsed = []
    for qr in results:
        if not isinstance(qr, dict):
            continue
        query_name = qr.get("query_name") or "unknown"
        label = qr.get("label") or query_name
        data = qr.get("data")
        if qr.get("error") or data is None:
            continue

        rows = _extract_table_rows(data)
        if not rows:
            parsed.append({
                "id": f"shopify:{query_name}",
                "title": f"Shopify: {label}",
                "snippet": f"No data returned for {label}",
                "url": "https://admin.shopify.com/",
                "source_domain": "shopify.com",
                "date": None,
                "relevance": 0.5,
                "why_relevant": f"Shopify store analytics — {label}",
                "metadata": {
                    "signal_type": "store_analytics",
                    "query_type": query_name,
                    "row_count": 0,
                },
            })
            continue

        topic_rows = rows
        if query:
            topic_lower = query.lower()
            topic_rows = [r for r in rows if _row_matches_topic(r, topic_lower)]
            if not topic_rows:
                topic_rows = rows[:10]

        for i, row in enumerate(topic_rows[:20]):
            row_title = _row_title(row, label)
            snippet = _row_snippet(row)

            parsed.append({
                "id": f"shopify:{query_name}:{i}",
                "title": row_title[:200],
                "snippet": snippet[:500],
                "url": "https://admin.shopify.com/",
                "source_domain": "shopify.com",
                "date": None,
                "relevance": max(0.4, 0.85 - (i * 0.03)),
                "why_relevant": f"Shopify {label} for '{query[:40]}'" if query else label,
                "metadata": {
                    "signal_type": "store_analytics",
                    "query_type": query_name,
                    **{k: v for k, v in row.items() if k and v is not None},
                },
            })

    return parsed


def _extract_table_rows(data: dict | Any) -> list[dict[str, Any]]:
    """Extract rows from Shopify GraphQL response (TableResponse or PolarisViz)."""
    if not isinstance(data, dict):
        return []

    gql_data = data.get("data", data)
    if isinstance(gql_data, dict):
        gql_data = gql_data.get("shopifyqlQuery", gql_data)

    if not isinstance(gql_data, dict):
        return []

    table_data = gql_data.get("tableData")
    if isinstance(table_data, dict):
        columns = table_data.get("columns") or []
        col_names = [c.get("name", f"col_{i}") for i, c in enumerate(columns)] if isinstance(columns, list) else []
        row_data = table_data.get("rowData") or []
        if isinstance(row_data, list) and col_names:
            rows = []
            for rd in row_data:
                if isinstance(rd, list):
                    row = {}
                    for j, val in enumerate(rd):
                        if j < len(col_names):
                            row[col_names[j]] = val
                    rows.append(row)
            return rows

    viz_data = gql_data.get("data")
    if isinstance(viz_data, list):
        rows = []
        for series in viz_data:
            if isinstance(series, dict):
                key = series.get("key", "")
                for dp in series.get("data", []):
                    if isinstance(dp, dict):
                        rows.append({"series": key, **dp})
        return rows

    return []


def _row_matches_topic(row: dict, topic_lower: str) -> bool:
    for val in row.values():
        if isinstance(val, str) and topic_lower in val.lower():
            return True
    return False


def _row_title(row: dict, label: str) -> str:
    for key in ("product_title", "channel_title", "series", "key"):
        val = row.get(key)
        if val and isinstance(val, str):
            return f"Shopify: {val}"
    return f"Shopify: {label}"


def _row_snippet(row: dict) -> str:
    parts = []
    for k, v in row.items():
        if k in ("product_title", "channel_title", "series", "key"):
            continue
        if v is not None:
            parts.append(f"{k}: {v}")
    return " · ".join(parts[:6]) or "Shopify analytics data"
