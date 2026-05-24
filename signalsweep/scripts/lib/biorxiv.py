"""bioRxiv preprint search via api.biorxiv.org (signalsweep 3.6+).

Also the shared backend implementation for medRxiv — medrxiv.py imports the
core search/parse helpers and only differs in the `server` parameter.

No auth required. JSON. Returns recent preprints by date-range; client-side
filters on topic match against title + abstract since the API doesn't support
topic search.
"""

from __future__ import annotations

from typing import Any

from . import public_api


DETAILS_URL = "https://api.biorxiv.org/details/{server}/{from_date}/{to_date}/0"

DEPTH_LIMITS = {
    "quick": 10,
    "default": 30,
    "deep": 75,
}


def _topic_tokens(topic: str) -> set[str]:
    """Simple lowercase tokens for substring matching."""
    return {t.strip().lower() for t in topic.split() if len(t.strip()) >= 3}


def _matches_topic(preprint: dict[str, Any], tokens: set[str]) -> bool:
    if not tokens:
        return True
    hay = f"{preprint.get('title', '')} {preprint.get('abstract', '')}".lower()
    return any(tok in hay for tok in tokens)


def search_preprint_server(
    server: str,
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch preprints from biorxiv or medrxiv and client-side filter by topic."""
    url = DETAILS_URL.format(server=server, from_date=from_date, to_date=to_date)
    raw = public_api.fetch_json(
        url,
        cache_key=f"{server}:{from_date}:{to_date}",
        user_agent_suffix=f"({server}-adapter)",
    )
    if raw.get("error") or not raw.get("items"):
        return raw
    return raw  # caller will filter + slice in parse_*


def search_biorxiv(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return search_preprint_server("biorxiv", topic, from_date, to_date, depth, config)


def _parse_preprint_collection(
    response: dict[str, Any],
    server: str,
    query: str,
    max_items: int,
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    collection = response["items"].get("collection", []) or []
    tokens = _topic_tokens(query)

    parsed = []
    for preprint in collection:
        if not _matches_topic(preprint, tokens):
            continue

        title = (preprint.get("title") or "").strip()
        abstract = (preprint.get("abstract") or "").strip()
        doi = (preprint.get("doi") or "").strip()
        date = (preprint.get("date") or "").strip()
        category = (preprint.get("category") or "").strip()
        authors = (preprint.get("authors") or "").strip()

        if not title or not doi:
            continue

        url = f"https://www.{server}.org/content/{doi}v{preprint.get('version', '1')}"
        first_author = authors.split(";")[0].strip() if authors else ""
        domain = f"{server}.org"

        parsed.append({
            "id": doi,
            "title": title,
            "snippet": abstract[:500],
            "url": url,
            "date": date,
            "source_domain": domain,
            "relevance": 0.7,
            "why_relevant": f"{server} preprint in {category}" if category else f"{server} preprint",
            "metadata": {
                "doi": doi,
                "category": category,
                "first_author": first_author,
                "all_authors": authors,
                "version": preprint.get("version", ""),
                "corresponding_institution": preprint.get("author_corresponding_institution", ""),
                "server": server,
            },
        })
        if len(parsed) >= max_items:
            break
    return parsed


def parse_biorxiv_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    max_items = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    return _parse_preprint_collection(response, "biorxiv", query, max_items)
