"""Semantic Scholar paper search via api.semanticscholar.org (signalsweep 3.6+).

No auth required; optional free API key raises the rate limit from ~100 req/5min
to 1 req/sec. Pulled from config as SEMANTIC_SCHOLAR_API_KEY when present.
"""

from __future__ import annotations

from typing import Any

from . import public_api


SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

DEPTH_LIMITS = {
    "quick": 10,
    "default": 25,
    "deep": 50,
}

REQUESTED_FIELDS = "title,abstract,year,authors,citationCount,url,externalIds,venue,publicationDate"


def search_semantic_scholar(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    from_year = (from_date or "")[:4]
    to_year = (to_date or "")[:4]
    year_filter = f"{from_year}-{to_year}" if from_year and to_year else ""

    params: dict[str, Any] = {
        "query": topic,
        "limit": limit,
        "fields": REQUESTED_FIELDS,
    }
    if year_filter:
        params["year"] = year_filter

    extra_headers: dict[str, str] = {}
    api_key = (config or {}).get("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        extra_headers["x-api-key"] = api_key

    return public_api.fetch_json(
        SEARCH_URL,
        params=params,
        cache_key=f"semantic_scholar:{topic}:{from_year}:{to_year}:{depth}",
        user_agent_suffix="(semantic-scholar-adapter)",
        extra_headers=extra_headers or None,
    )


def _first_author(authors: list[dict[str, Any]] | None) -> str:
    if not authors:
        return ""
    name = (authors[0] or {}).get("name") or ""
    return name.strip()


def parse_semantic_scholar_response(
    response: dict[str, Any],
    query: str = "",
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    papers = response["items"].get("data") or []
    parsed = []
    for paper in papers:
        title = (paper.get("title") or "").strip()
        abstract = (paper.get("abstract") or "").strip()
        url = (paper.get("url") or "").strip()
        venue = (paper.get("venue") or "").strip()
        cits = paper.get("citationCount") or 0
        authors = paper.get("authors") or []
        pub_date = (paper.get("publicationDate") or "").strip()
        year = paper.get("year") or ""
        external_ids = paper.get("externalIds") or {}
        doi = external_ids.get("DOI") or ""
        paper_id = paper.get("paperId") or doi or url

        if not title or not url:
            continue

        parsed.append({
            "id": paper_id,
            "title": title,
            "snippet": abstract[:500],
            "url": url,
            "date": pub_date or (f"{year}-01-01" if year else None),
            "source_domain": "semanticscholar.org",
            "relevance": 0.7,
            "why_relevant": f"Scholarly paper ({cits} citations)" if cits else "Scholarly paper",
            "engagement": {"citation_count": cits},
            "metadata": {
                "paper_id": paper_id,
                "doi": doi,
                "venue": venue,
                "year": year,
                "citation_count": cits,
                "first_author": _first_author(authors),
                "all_authors": [(a or {}).get("name", "") for a in authors],
            },
        })
    return parsed
