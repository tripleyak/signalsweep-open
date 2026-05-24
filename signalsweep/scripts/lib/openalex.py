"""OpenAlex scholarly works search via api.openalex.org (signalsweep 3.6+).

No auth required. Free tier: 100K requests/day in the polite pool when a mailto
email is provided. We always include `mailto` (from OPENALEX_CONTACT_EMAIL config
or a default) so every call qualifies for the polite pool.
"""

from __future__ import annotations

from typing import Any

from . import public_api


SEARCH_URL = "https://api.openalex.org/works"

DEPTH_LIMITS = {
    "quick": 10,
    "default": 25,
    "deep": 50,
}


def search_openalex(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    mailto = (config or {}).get("OPENALEX_CONTACT_EMAIL") or "contact@signalsweep.dev"

    filter_parts = []
    if from_date:
        filter_parts.append(f"from_publication_date:{from_date}")
    if to_date:
        filter_parts.append(f"to_publication_date:{to_date}")

    params: dict[str, Any] = {
        "search": topic,
        "per-page": limit,
        "mailto": mailto,
    }
    if filter_parts:
        params["filter"] = ",".join(filter_parts)

    return public_api.fetch_json(
        SEARCH_URL,
        params=params,
        cache_key=f"openalex:{topic}:{from_date}:{to_date}:{depth}",
        user_agent_suffix=f"(openalex-adapter mailto:{mailto})",
    )


def _first_author_and_authors(authorships: list[dict[str, Any]] | None) -> tuple[str, list[str]]:
    if not authorships:
        return "", []
    names = []
    for a in authorships:
        author = (a or {}).get("author") or {}
        name = (author.get("display_name") or "").strip()
        if name:
            names.append(name)
    return (names[0] if names else ""), names


def parse_openalex_response(response: dict[str, Any], query: str = "") -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    works = response["items"].get("results") or []
    parsed = []
    for work in works:
        title = (work.get("title") or work.get("display_name") or "").strip()
        abstract_inv = work.get("abstract_inverted_index") or {}
        # OpenAlex returns abstracts as an inverted index (position → word map).
        # Rebuild a rough abstract preview by sorting positions.
        if abstract_inv and isinstance(abstract_inv, dict):
            positions = []
            for word, idxs in abstract_inv.items():
                for i in idxs or []:
                    positions.append((i, word))
            positions.sort()
            abstract = " ".join(word for _, word in positions[:200])
        else:
            abstract = ""

        oa_id = (work.get("id") or "").strip()
        doi = (work.get("doi") or "").replace("https://doi.org/", "").strip()
        pub_date = (work.get("publication_date") or "").strip()
        cits = work.get("cited_by_count") or 0
        venue_dict = work.get("primary_location") or {}
        venue_source = (venue_dict.get("source") or {})
        venue = (venue_source.get("display_name") or "").strip()
        first_author, all_authors = _first_author_and_authors(work.get("authorships"))

        # Prefer DOI url if present, else OpenAlex work URL
        url = f"https://doi.org/{doi}" if doi else oa_id
        if not title or not url:
            continue

        parsed.append({
            "id": oa_id,
            "title": title,
            "snippet": (abstract or title)[:500],
            "url": url,
            "date": pub_date or None,
            "source_domain": "openalex.org",
            "relevance": 0.7,
            "why_relevant": f"OpenAlex work ({cits} citations)" if cits else "OpenAlex work",
            "engagement": {"citation_count": cits},
            "metadata": {
                "openalex_id": oa_id,
                "doi": doi,
                "venue": venue,
                "publication_date": pub_date,
                "citation_count": cits,
                "first_author": first_author,
                "all_authors": all_authors,
                "type": work.get("type"),
                "is_oa": bool((work.get("open_access") or {}).get("is_oa")),
            },
        })
    return parsed
