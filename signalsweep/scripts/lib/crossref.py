"""CrossRef works search (signalsweep 3.6.1+).

No auth required. CrossRef requests a `mailto=` in the User-Agent header
to qualify for the polite request pool (faster + more reliable). We pass
this via `user_agent_suffix`.

Endpoint: https://api.crossref.org/works?query=<topic>&rows=<N>
"""

from __future__ import annotations

from typing import Any

from . import public_api


SEARCH_URL = "https://api.crossref.org/works"

# CrossRef requests this attribution per their polite-pool guidelines.
POLITE_MAILTO = "signalsweep@tripleyak.dev"

DEPTH_LIMITS = {
    "quick": 10,
    "default": 25,
    "deep": 50,
}


def search_crossref(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search CrossRef works by topic."""
    rows = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    params = {
        "query": topic,
        "rows": rows,
        "select": "DOI,title,abstract,author,published-print,published-online,container-title,publisher,URL,subject,type",
    }
    return public_api.fetch_json(
        SEARCH_URL,
        params=params,
        cache_key=f"crossref:{topic}:{depth}",
        user_agent_suffix=f"(crossref-adapter; mailto:{POLITE_MAILTO})",
    )


def _published_date(work: dict[str, Any]) -> str:
    """CrossRef stores dates as nested date-parts arrays. Prefer print, fall back to online."""
    for key in ("published-print", "published-online", "issued"):
        date_field = work.get(key)
        if not isinstance(date_field, dict):
            continue
        parts = date_field.get("date-parts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
            comps = [str(p).zfill(2) for p in parts[0]]
            # CrossRef parts are [Y, M, D] but M and D may be missing
            year = comps[0] if len(comps) >= 1 else ""
            month = comps[1] if len(comps) >= 2 else "01"
            day = comps[2] if len(comps) >= 3 else "01"
            if year and len(year) == 4:
                return f"{year}-{month}-{day}"
    return ""


def _author_string(work: dict[str, Any]) -> str:
    """Format first author as 'Family, Given'; for >1 author, append 'et al.'"""
    authors = work.get("author") or []
    if not isinstance(authors, list) or not authors:
        return ""
    first = authors[0] or {}
    family = (first.get("family") or "").strip()
    given = (first.get("given") or "").strip()
    name_parts = [p for p in (family, given) if p]
    name = ", ".join(name_parts) if name_parts else "Unknown"
    if len(authors) > 1:
        return f"{name} et al."
    return name


def parse_crossref_response(
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

    message = payload.get("message") or {}
    works = message.get("items") or []
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []
    for work in works:
        if not isinstance(work, dict):
            continue
        doi = (work.get("DOI") or "").strip()
        title_list = work.get("title") or []
        title = (title_list[0] if title_list else "").strip()
        if not doi or not title:
            continue

        abstract = (work.get("abstract") or "").strip()
        # CrossRef abstracts may be wrapped in <jats:p> tags; rough strip
        if abstract.startswith("<jats:p>") and abstract.endswith("</jats:p>"):
            abstract = abstract[len("<jats:p>"):-len("</jats:p>")]

        container_list = work.get("container-title") or []
        container = (container_list[0] if container_list else "").strip()
        publisher = (work.get("publisher") or "").strip()
        url = (work.get("URL") or f"https://doi.org/{doi}").strip()
        date = _published_date(work)
        work_type = (work.get("type") or "").strip()
        author = _author_string(work)

        parsed.append({
            "id": doi,
            "title": title,
            "snippet": abstract[:500],
            "url": url,
            "date": date or None,
            "source_domain": "crossref.org",
            "author": author,
            "relevance": 0.65,
            "why_relevant": f"CrossRef {work_type}: {container}" if container else f"CrossRef {work_type}",
            "metadata": {
                "doi": doi,
                "container": container,
                "publisher": publisher,
                "type": work_type,
                "subjects": work.get("subject") or [],
            },
        })
        if len(parsed) >= limit:
            break
    return parsed
