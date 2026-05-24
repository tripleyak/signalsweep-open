"""Google Trends (signalsweep 3.9.0+).

Google Trends via the community `pytrends` library. Google deprecated the
official Trends API years ago; `pytrends` is the de-facto community client,
actively maintained.

No auth required. pytrends handles User-Agent + cookie state internally.

Library: github.com/GeneralMills/pytrends — pinned in pyproject.toml.
"""

from __future__ import annotations

from typing import Any

from . import demand_signals


DEPTH_LIMITS = {"quick": 5, "default": 15, "deep": 30}

DEFAULT_GEO = ""  # worldwide by default; override via GOOGLE_TRENDS_GEO


def _timeframe(from_date: str, to_date: str) -> str:
    """Build pytrends-style timeframe 'YYYY-MM-DD YYYY-MM-DD'."""
    if from_date and to_date:
        return f"{from_date} {to_date}"
    return "today 3-m"  # pytrends default fallback


def search_google_trends(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not demand_signals.is_demand_signals_enabled(config):
        return demand_signals.disabled_envelope()

    # Lazy import so adapter can be imported without pytrends installed.
    try:
        from pytrends.request import TrendReq  # type: ignore
    except ImportError:
        return {"items": None, "error": "library_missing"}

    geo = (config.get("GOOGLE_TRENDS_GEO") or DEFAULT_GEO).upper() if config.get("GOOGLE_TRENDS_GEO") else DEFAULT_GEO
    timeframe = _timeframe(from_date, to_date)

    try:
        pytrends = TrendReq(hl="en-US", tz=0, timeout=(10, 25))
        pytrends.build_payload([topic], timeframe=timeframe, geo=geo)
        df = pytrends.interest_over_time()
    except Exception as exc:  # pytrends raises ResponseError + generic urllib errors
        msg = str(exc).lower()
        if "429" in msg or "rate" in msg or "too many" in msg:
            return demand_signals.rate_limited_envelope()
        return {"items": None, "error": f"pytrends_error: {type(exc).__name__}"}

    # df is a pandas DataFrame; serialize to list-of-tuples to avoid leaking pandas.
    if df is None or getattr(df, "empty", True):
        return {"items": {"topic": topic, "series": [], "geo": geo}, "error": None}

    series: list[tuple[str, int]] = []
    try:
        for ts, value in df[topic].items():
            ts_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
            series.append((ts_str, int(value)))
    except (KeyError, AttributeError):
        return {"items": {"topic": topic, "series": [], "geo": geo}, "error": None}

    return {"items": {"topic": topic, "series": series, "geo": geo}, "error": None}


def parse_google_trends_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    payload = response["items"]
    if not isinstance(payload, dict):
        return []

    topic = payload.get("topic") or query
    series = payload.get("series") or []
    geo = payload.get("geo") or ""

    if not topic or not series:
        return []

    values = [v for _, v in series if isinstance(v, (int, float))]
    if not values:
        return []

    peak = max(values)
    avg = sum(values) / len(values) if values else 0.0
    peak_idx = values.index(peak)
    peak_ts = series[peak_idx][0] if peak_idx < len(series) else ""

    snippet = (
        f"Google Trends interest for '{topic}' ({geo or 'worldwide'}): "
        f"peak {peak} on {peak_ts}, avg {avg:.1f} across {len(values)} points."
    )

    item = demand_signals.build_trend_item(
        item_id=f"google_trends:{topic}:{geo}",
        title=f"Google Trends: {topic}",
        snippet=snippet,
        url=f"https://trends.google.com/trends/explore?q={topic.replace(' ', '+')}&geo={geo}",
        source_domain="trends.google.com",
        relevance=0.7,
        why_relevant=f"Search-interest trajectory for '{topic}'",
        engagement_score=float(peak),
        date=to_date or None,
        metadata={
            "topic": topic,
            "geo": geo,
            "time_series": series,
            "peak_value": peak,
            "peak_date": peak_ts,
            "avg_value": avg,
            "data_points": len(values),
        },
    )
    return [item]
