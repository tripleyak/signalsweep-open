"""Wayback Machine CDX — historical snapshots of any URL (signalsweep 3.16.4+).

Internet Archive's CDX Server API surfaces archived snapshots for any URL or
domain. Free, stable, no auth. One of the most stable research APIs in
existence (CDX stable since 2013).

**Use cases:**
- Competitor landing-page evolution (month-by-month captures)
- Messaging / pricing change detection
- Product-page launch-date detection (first snapshot = went live)
- Whole-site backfill when a page is deleted
- Pairs with v3.16.0-v3.16.3 ad libraries: ad → landing page → historical archaeology

Endpoint: https://web.archive.org/cdx/search/cdx

Tier: v3.6 public-data (gated by `SIGNALSWEEP_DISABLE_PUBLIC_APIS`).

Docs: github.com/internetarchive/wayback/blob/master/wayback-cdx-server-webapp/README.md
"""

from __future__ import annotations

from typing import Any

from . import public_api


DEFAULT_ENDPOINT = "https://web.archive.org/cdx/search/cdx"

DEPTH_LIMITS = {"quick": 25, "default": 100, "deep": 500}

DEFAULT_COLLAPSE = "timestamp:6"  # monthly snapshots


def _infer_match_type(topic: str, override: str) -> str:
    """If override is set use it; else infer exact vs domain from topic shape."""
    if override:
        return override.strip().lower()
    # Heuristic: full URL → exact; bare hostname (no path, no scheme) → domain.
    if "://" in topic or "/" in topic:
        return "exact"
    return "domain"


def _format_cdx_date(date_str: str) -> str:
    """Convert YYYY-MM-DD to YYYYMMDD; passthrough if already compact."""
    if not date_str:
        return ""
    return date_str.replace("-", "")[:8]


def search_wayback_machine_cdx(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not public_api.is_public_apis_enabled(config):
        return {"items": None, "error": "public_apis_disabled"}

    match_type_override = config.get("WAYBACK_MATCH_TYPE") or ""
    match_type = _infer_match_type(topic, match_type_override)
    collapse = config.get("WAYBACK_COLLAPSE") or DEFAULT_COLLAPSE
    cdx_filter = config.get("WAYBACK_FILTER") or ""
    endpoint = config.get("WAYBACK_ENDPOINT") or DEFAULT_ENDPOINT
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    params: dict[str, Any] = {
        "url": topic,
        "output": "json",
        "matchType": match_type,
        "limit": limit,
    }
    if collapse:
        params["collapse"] = collapse
    if cdx_filter:
        params["filter"] = cdx_filter
    if from_date:
        params["from"] = _format_cdx_date(from_date)
    if to_date:
        params["to"] = _format_cdx_date(to_date)

    return public_api.fetch_json(
        endpoint,
        params=params,
        cache_key=f"wayback_cdx:{topic}:{match_type}:{from_date}:{to_date}:{collapse}:{depth}",
        cache_ttl_hours=24,
        user_agent_suffix="(wayback_machine_cdx-adapter)",
    )


def parse_wayback_machine_cdx_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    payload = response["items"]
    # CDX json output: list-of-lists; first row is headers.
    if not isinstance(payload, list):
        return []
    if len(payload) < 2:
        return []

    headers = payload[0]
    if not isinstance(headers, list):
        return []
    rows = payload[1:]

    # Header field indices (CDX canonical order):
    # urlkey, timestamp, original, mimetype, statuscode, digest, length
    def _idx(name: str) -> int:
        try:
            return headers.index(name)
        except ValueError:
            return -1

    idx_timestamp = _idx("timestamp")
    idx_original = _idx("original")
    idx_mime = _idx("mimetype")
    idx_status = _idx("statuscode")
    idx_digest = _idx("digest")
    idx_length = _idx("length")

    if idx_timestamp < 0 or idx_original < 0:
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for row in rows[:limit]:
        if not isinstance(row, list) or len(row) <= max(idx_timestamp, idx_original):
            continue
        timestamp = str(row[idx_timestamp] or "")
        original = str(row[idx_original] or "")
        if not timestamp or not original:
            continue

        mime = str(row[idx_mime] or "") if idx_mime >= 0 and idx_mime < len(row) else ""
        status = str(row[idx_status] or "") if idx_status >= 0 and idx_status < len(row) else ""
        digest = str(row[idx_digest] or "") if idx_digest >= 0 and idx_digest < len(row) else ""
        length = str(row[idx_length] or "") if idx_length >= 0 and idx_length < len(row) else ""

        # YYYYMMDDhhmmss → YYYY-MM-DD
        date_iso = None
        if len(timestamp) >= 8 and timestamp[:8].isdigit():
            date_iso = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}"

        archive_url = f"https://web.archive.org/web/{timestamp}/{original}"

        snippet_parts = []
        if mime:
            snippet_parts.append(mime)
        if status:
            snippet_parts.append(f"HTTP {status}")
        if length:
            snippet_parts.append(f"{length} bytes")
        snippet = " · ".join(snippet_parts) or f"Archived snapshot"

        title = f"{original} @ {date_iso or timestamp}"

        parsed.append({
            "id": f"wayback:{timestamp}:{digest[:12]}" if digest else f"wayback:{timestamp}",
            "title": title[:200],
            "snippet": snippet,
            "url": archive_url,
            "source_domain": "web.archive.org",
            "date": date_iso,
            "relevance": 0.65,
            "why_relevant": f"Historical snapshot of {original[:80]}",
            "metadata": {
                "snapshot_timestamp": timestamp,
                "original_url": original,
                "mimetype": mime,
                "statuscode": status,
                "digest": digest,
                "length": length,
                "archive_url": archive_url,
            },
        })
    return parsed
