"""Shared helper for v3.9+ demand-signal sources (signalsweep 3.9.0+).

Parallels `public_api.py` (v3.6 no-auth) and `paid_api.py` (v3.7 paid) but
purpose-built for search-trend / autocomplete / question-phrased-demand
sources. Key provisions:

- `is_demand_signals_enabled(config)` master toggle via
  SIGNALSWEEP_DISABLE_DEMAND_SIGNALS env var.
- `credentials_missing_envelope()` / `credentials_invalid_envelope()` /
  `rate_limited_envelope()` helpers for consistent error shapes.
- `fetch_trends_json(url, ...)` — thin wrapper on `public_api.fetch_json`
  with optional bearer-token auth; returns the same `{"items": ..., "error": ...}`
  shape.

TOS boundary note: v3.9.0 scrapes public-facing tools (Pinterest Trends,
TikTok Creative Center, Soovle, etc.) respectfully — no browser automation,
conservative rate-limiting via per-adapter sleeps where documented, and the
SIGNALSWEEP_DISABLE_DEMAND_SIGNALS escape hatch.
"""

from __future__ import annotations

import time
from typing import Any

from . import public_api


def is_demand_signals_enabled(config: dict[str, Any]) -> bool:
    """False when SIGNALSWEEP_DISABLE_DEMAND_SIGNALS is truthy. Else True.

    Truthy: '1' / 'true' / 'yes' (case-insensitive).
    """
    value = str(config.get("SIGNALSWEEP_DISABLE_DEMAND_SIGNALS", "")).strip().lower()
    return value not in {"1", "true", "yes"}


# ---------------------------------------------------------------------------
# Error envelopes (matches v3.7 paid_api.py conventions)
# ---------------------------------------------------------------------------

def credentials_missing_envelope() -> dict[str, Any]:
    return {"items": None, "error": "credentials_missing"}


def credentials_invalid_envelope() -> dict[str, Any]:
    return {"items": None, "error": "credentials_invalid"}


def rate_limited_envelope() -> dict[str, Any]:
    return {"items": None, "error": "rate_limited"}


def disabled_envelope() -> dict[str, Any]:
    return {"items": None, "error": "demand_signals_disabled"}


def empty_response_envelope() -> dict[str, Any]:
    return {"items": None, "error": "empty_response"}


# ---------------------------------------------------------------------------
# Request wrapper
# ---------------------------------------------------------------------------

def fetch_trends_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    bearer_token: str | None = None,
    cache_key: str | None = None,
    cache_ttl_hours: int = 24,
    user_agent_suffix: str = "",
    extra_headers: dict[str, str] | None = None,
    polite_sleep_ms: int = 0,
) -> dict[str, Any]:
    """Thin wrapper on public_api.fetch_json with optional bearer auth.

    - `bearer_token` — if provided, adds `Authorization: Bearer <token>` header.
    - `polite_sleep_ms` — optional per-call sleep to respect rate limits for
      TOS-sensitive public tools (e.g., TikTok Creative Center). Runs AFTER
      the request, so consecutive calls are throttled.

    Returns `{"items": <parsed>, "error": None|str}` matching public_api.
    """
    headers: dict[str, str] = dict(extra_headers or {})
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    result = public_api.fetch_json(
        url,
        params=params,
        cache_key=cache_key,
        cache_ttl_hours=cache_ttl_hours,
        user_agent_suffix=user_agent_suffix,
        extra_headers=headers or None,
    )

    if polite_sleep_ms > 0:
        time.sleep(polite_sleep_ms / 1000.0)

    return result


def build_trend_item(
    *,
    item_id: str,
    title: str,
    snippet: str,
    url: str,
    source_domain: str,
    relevance: float = 0.6,
    why_relevant: str = "",
    engagement_score: float = 0.0,
    date: str | None = None,
    author: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standard SourceItem dict from trend-source data.

    Trend-specific fields (trend score, time-series, query metadata) land
    in `metadata`. Top-level fields follow the v3.6 contract expected by
    `normalize._normalize_grounding`.
    """
    item = {
        "id": item_id,
        "title": title[:200] if title else item_id,
        "snippet": (snippet or "")[:500],
        "url": url or "",
        "date": date,
        "source_domain": source_domain,
        "relevance": relevance,
        "why_relevant": why_relevant or title[:60],
        "engagement_score": engagement_score,
        "metadata": metadata or {},
    }
    if author:
        item["author"] = author
    return item
