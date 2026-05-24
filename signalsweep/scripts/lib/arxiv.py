"""arXiv preprint search via export.arxiv.org/api/query (signalsweep 3.6+).

No auth required. Atom XML response. Rate limit: 1 request / 3 sec (polite usage).

arXiv API doesn't support native date filtering in the search query, so we sort
by submittedDate desc and filter client-side against from_date/to_date. For broad
queries this means we may need to fetch more entries than we return — scale the
max_results by depth to keep the effective recall reasonable.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from . import public_api


SEARCH_URL = "https://export.arxiv.org/api/query"

# Atom + arXiv-specific namespaces
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

DEPTH_LIMITS = {
    "quick": 15,
    "default": 40,
    "deep": 100,
}


def search_arxiv(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search arXiv for papers matching topic. Returns public_api envelope."""
    max_results = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {
        "search_query": f"all:{topic}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    return public_api.fetch_xml(
        SEARCH_URL,
        params=params,
        user_agent_suffix="(arxiv-adapter)",
    )


def _text(elem: ET.Element | None, path: str, default: str = "") -> str:
    if elem is None:
        return default
    found = elem.findtext(path, default=default, namespaces=NS)
    return (found or "").strip()


def _arxiv_id_from_url(raw_id: str) -> str:
    """Extract arxiv paper id from URL like 'http://arxiv.org/abs/2604.09541v1' → '2604.09541v1'."""
    return raw_id.rsplit("/", 1)[-1] if raw_id else ""


def _in_date_range(published: str, from_date: str, to_date: str) -> bool:
    """Check if published timestamp (YYYY-MM-DDTHH:MM:SSZ) is in [from, to]."""
    if not published:
        return True  # don't drop undated entries; downstream filter will decide
    pub_day = published[:10]
    return from_date <= pub_day <= to_date


def parse_arxiv_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
) -> list[dict[str, Any]]:
    """Parse arXiv Atom feed into list of normalized item dicts."""
    if response.get("error") or response.get("items") is None:
        return []

    root = response["items"]
    entries = root.findall("atom:entry", NS)

    parsed = []
    for entry in entries:
        title = _text(entry, "atom:title")
        summary = _text(entry, "atom:summary")
        published = _text(entry, "atom:published")

        # Date filter (client-side)
        if from_date and to_date and not _in_date_range(published, from_date, to_date):
            continue

        raw_id = _text(entry, "atom:id")
        arxiv_id = _arxiv_id_from_url(raw_id)
        abs_url = raw_id  # arXiv's atom id IS the abs URL

        author_elems = entry.findall("atom:author/atom:name", NS)
        authors = [(a.text or "").strip() for a in author_elems if a.text]
        first_author = authors[0] if authors else ""

        primary_category = entry.find("arxiv:primary_category", NS)
        category = primary_category.get("term", "") if primary_category is not None else ""

        if not title or not abs_url:
            continue

        parsed.append({
            "id": arxiv_id,
            "title": title,
            "snippet": summary[:400],
            "url": abs_url,
            "date": published[:10] if published else None,
            "source_domain": "arxiv.org",
            "relevance": 0.7,
            "why_relevant": f"arXiv preprint in {category}" if category else "arXiv preprint",
            "metadata": {
                "arxiv_id": arxiv_id,
                "primary_category": category,
                "authors": authors,
                "first_author": first_author,
                "all_categories": [
                    c.get("term", "") for c in entry.findall("atom:category", NS)
                ],
            },
        })
    return parsed
