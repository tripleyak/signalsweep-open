"""US Bureau of Labor Statistics catalog discovery (signalsweep 3.6+).

MVP: BLS doesn't expose a native text search API for series. We ship a curated
catalog of high-value series IDs and match the topic keywords against their
titles client-side. Full BLS series-search via scraping deferred to 3.6.1.

No auth required. Optional BLS_API_KEY raises data pull limits (not relevant
for this catalog-only MVP).
"""

from __future__ import annotations

from typing import Any

from . import public_api


# Curated high-value series — one entry per topic area.
# Expand via 3.6.1 or user-config additions.
CURATED_SERIES = [
    {"id": "CUUR0000SA0", "title": "Consumer Price Index (All Urban Consumers, all items)", "topic_tags": ["cpi", "inflation", "consumer", "prices", "cost"]},
    {"id": "LNS14000000", "title": "Unemployment Rate (US, seasonally adjusted)", "topic_tags": ["unemployment", "jobs", "labor", "jobless"]},
    {"id": "CES0000000001", "title": "Total Nonfarm Employment (All Employees, seasonally adjusted)", "topic_tags": ["jobs", "employment", "nonfarm", "payroll"]},
    {"id": "LNS11300000", "title": "Labor Force Participation Rate", "topic_tags": ["participation", "labor force"]},
    {"id": "CES0500000003", "title": "Average Hourly Earnings (Private nonfarm, seasonally adjusted)", "topic_tags": ["wage", "wages", "earnings", "income"]},
    {"id": "PRS85006092", "title": "Labor Productivity (Nonfarm business sector)", "topic_tags": ["productivity"]},
    {"id": "WPSFD49207", "title": "Producer Price Index (Final demand)", "topic_tags": ["ppi", "producer prices", "wholesale"]},
    {"id": "LNS12000000", "title": "Total Civilian Employment (seasonally adjusted)", "topic_tags": ["employment", "civilian"]},
    {"id": "JTU000000000000000JOL", "title": "Job Openings Total (JOLTS, seasonally adjusted)", "topic_tags": ["job openings", "jolts", "vacancies"]},
    {"id": "JTU000000000000000QUL", "title": "Quits Rate Total (JOLTS)", "topic_tags": ["quits", "turnover", "jolts"]},
]


def _matches(series: dict[str, Any], topic: str) -> bool:
    t = topic.lower()
    tags = set(series.get("topic_tags") or [])
    for tag in tags:
        if tag in t:
            return True
    return False


def search_bls(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Match topic against curated series catalog. No HTTP call in MVP."""
    matches = [s for s in CURATED_SERIES if _matches(s, topic)]
    return {"items": {"matches": matches, "date_range": [from_date, to_date]}, "error": None}


def parse_bls_response(response: dict[str, Any], query: str = "") -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    matches = response["items"].get("matches") or []
    date_range = response["items"].get("date_range") or ["", ""]
    parsed = []
    for series in matches:
        sid = series["id"]
        parsed.append({
            "id": sid,
            "title": series["title"],
            "snippet": f"BLS series {sid}. Fetch latest values via data.bls.gov/timeseries/{sid}.",
            "url": f"https://data.bls.gov/timeseries/{sid}",
            "date": date_range[1] or None,
            "source_domain": "bls.gov",
            "relevance": 0.65,
            "why_relevant": f"US Bureau of Labor Statistics — {series['title'][:60]}",
            "metadata": {
                "series_id": sid,
                "tags": series.get("topic_tags", []),
            },
        })
    return parsed
