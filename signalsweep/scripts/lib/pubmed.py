"""PubMed biomedical literature search via NCBI E-utilities (signalsweep 3.6+).

Two-step flow wrapped in a single `search_pubmed`:
  1. esearch.fcgi — returns list of PMIDs matching topic + date range
  2. esummary.fcgi — returns metadata for those PMIDs

No auth required (3 req/sec); optional NCBI_API_KEY bumps to 10 req/sec.
"""

from __future__ import annotations

from typing import Any

from . import public_api


ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

DEPTH_LIMITS = {
    "quick": 10,
    "default": 25,
    "deep": 50,
}


def _build_term(topic: str, from_date: str, to_date: str) -> str:
    """Compose esearch 'term' with date-published filter."""
    term = topic.strip()
    if from_date and to_date:
        # PubMed date-published format: YYYY/MM/DD
        fd = from_date.replace("-", "/")
        td = to_date.replace("-", "/")
        term = f"{term} AND {fd}:{td}[dp]"
    return term


def _api_key_param(config: dict[str, Any] | None) -> dict[str, str]:
    key = (config or {}).get("NCBI_API_KEY")
    return {"api_key": key} if key else {}


def search_pubmed(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Two-call flow: esearch → esummary. Returns unified envelope with per-PMID summaries."""
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    extras = _api_key_param(config)

    esearch_params = {
        "db": "pubmed",
        "term": _build_term(topic, from_date, to_date),
        "retmode": "json",
        "retmax": limit,
        "sort": "date",
        **extras,
    }
    esearch_resp = public_api.fetch_json(
        ESEARCH_URL,
        params=esearch_params,
        cache_key=f"pubmed-esearch:{topic}:{from_date}:{to_date}:{depth}",
        user_agent_suffix="(pubmed-adapter)",
    )

    if esearch_resp.get("error"):
        return esearch_resp
    if not esearch_resp.get("items"):
        return {"items": None, "error": "empty_response"}

    pmids = (
        esearch_resp["items"]
        .get("esearchresult", {})
        .get("idlist", [])
    )
    if not pmids:
        # No hits — return empty shape caller can parse
        return {"items": {"result": {"uids": []}}, "error": None}

    esummary_params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
        **extras,
    }
    esummary_resp = public_api.fetch_json(
        ESUMMARY_URL,
        params=esummary_params,
        cache_key=f"pubmed-esummary:{','.join(pmids)}",
        user_agent_suffix="(pubmed-adapter)",
    )
    return esummary_resp


def _first_author(authors: list[dict[str, Any]] | None) -> str:
    if not authors:
        return ""
    return (authors[0] or {}).get("name", "").strip()


def parse_pubmed_response(response: dict[str, Any], query: str = "") -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    result = response["items"].get("result") or {}
    uids = result.get("uids") or []

    parsed = []
    for pmid in uids:
        entry = result.get(pmid) or {}
        title = (entry.get("title") or "").strip().rstrip(".")
        journal = (entry.get("fulljournalname") or entry.get("source") or "").strip()
        pubdate_raw = (entry.get("pubdate") or "").strip()
        # Try to coerce "2026 Apr 2" or "2026" into YYYY-MM-DD
        pubdate = _coerce_pubdate(pubdate_raw)
        authors = entry.get("authors") or []
        mesh = entry.get("meshheadinglist") or []
        article_ids = entry.get("articleids") or []
        doi = next(
            ((a.get("value") or "").strip() for a in article_ids if a.get("idtype") == "doi"),
            "",
        )

        if not title:
            continue

        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        parsed.append({
            "id": pmid,
            "title": title,
            "snippet": title,  # esummary doesn't return full abstract; caller could efetch for it
            "url": url,
            "date": pubdate,
            "source_domain": "pubmed.ncbi.nlm.nih.gov",
            "relevance": 0.7,
            "why_relevant": f"PubMed article in {journal}" if journal else "PubMed article",
            "metadata": {
                "pmid": pmid,
                "doi": doi,
                "journal": journal,
                "first_author": _first_author(authors),
                "mesh_terms": mesh,
                "all_authors": [(a or {}).get("name", "") for a in authors],
            },
        })
    return parsed


_MONTH_TO_NUM = {
    m.lower(): i for i, m in enumerate(
        ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    )
}


def _coerce_pubdate(raw: str) -> str | None:
    """Best-effort convert 'YYYY Mon DD' or 'YYYY Mon' or 'YYYY' to YYYY-MM-DD."""
    if not raw:
        return None
    parts = raw.split()
    if not parts:
        return None
    year = parts[0]
    if not (year.isdigit() and len(year) == 4):
        return None
    month = "01"
    day = "01"
    if len(parts) >= 2:
        mon_key = parts[1].lower()[:3]
        if mon_key in _MONTH_TO_NUM:
            month = f"{_MONTH_TO_NUM[mon_key]:02d}"
    if len(parts) >= 3 and parts[2].isdigit():
        day = f"{int(parts[2]):02d}"
    return f"{year}-{month}-{day}"


# ---------------------------------------------------------------------------
# PubMed efetch extension (signalsweep 3.6.1+)
# ---------------------------------------------------------------------------
#
# `search_pubmed` (above) returns titles + metadata only (esearch → esummary).
# `search_pubmed_efetch` swaps esummary for efetch, returning full abstract
# bodies in XML. ~10x more bytes per PMID — opt-in via separate dispatch
# source `pubmed_efetch`.
#
# Endpoint: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi

EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def search_pubmed_efetch(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """esearch → efetch flow. Returns XML envelope with full <PubmedArticle> records."""
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    extras = _api_key_param(config)

    esearch_params = {
        "db": "pubmed",
        "term": _build_term(topic, from_date, to_date),
        "retmode": "json",
        "retmax": limit,
        "sort": "date",
        **extras,
    }
    esearch_resp = public_api.fetch_json(
        ESEARCH_URL,
        params=esearch_params,
        cache_key=f"pubmed-efetch-esearch:{topic}:{from_date}:{to_date}:{depth}",
        user_agent_suffix="(pubmed_efetch-adapter)",
    )

    if esearch_resp.get("error"):
        return esearch_resp
    if not esearch_resp.get("items"):
        return {"items": None, "error": "empty_response"}

    pmids = (
        esearch_resp["items"]
        .get("esearchresult", {})
        .get("idlist", [])
    )
    if not pmids:
        return {"items": {"PubmedArticleSet": {"PubmedArticle": []}}, "error": None}

    efetch_params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": "abstract",
        "retmode": "xml",
        **extras,
    }
    return public_api.fetch_xml(
        EFETCH_URL,
        params=efetch_params,
        cache_key=f"pubmed-efetch:{','.join(pmids)}",
        user_agent_suffix="(pubmed_efetch-adapter)",
    )


def _xml_text(elem: Any, tag: str) -> str:
    """Return concatenated text of first matching child element, or empty string."""
    if elem is None:
        return ""
    found = elem.find(tag)
    if found is None:
        return ""
    # Concatenate all text including nested element text (e.g. <i>italic</i> within <AbstractText>)
    return "".join(found.itertext()).strip()


def _xml_findall_text(elem: Any, tag: str) -> list[str]:
    """Return list of text contents for all matching child elements."""
    if elem is None:
        return []
    return ["".join(c.itertext()).strip() for c in elem.findall(tag)]


def parse_pubmed_efetch_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    if response.get("error"):
        return []

    root = response.get("items")
    # public_api.fetch_xml returns the parsed ElementTree root element directly
    # under "items"; if not, treat as empty. (Note: avoid `not root` truth-check —
    # ElementTree elements deprecate boolean coercion.)
    if root is None or not hasattr(root, "findall"):
        return []

    parsed = []
    for article in root.findall(".//PubmedArticle"):
        medline = article.find("MedlineCitation")
        if medline is None:
            continue
        pmid_elem = medline.find("PMID")
        pmid = (pmid_elem.text or "").strip() if pmid_elem is not None else ""
        if not pmid:
            continue

        article_elem = medline.find("Article")
        if article_elem is None:
            continue

        title = _xml_text(article_elem, "ArticleTitle")
        # Abstract may have multiple <AbstractText> sections (BACKGROUND/METHODS/RESULTS)
        abstract_elem = article_elem.find("Abstract")
        abstract_parts = _xml_findall_text(abstract_elem, "AbstractText")
        abstract = " ".join(p for p in abstract_parts if p)

        journal_elem = article_elem.find("Journal")
        journal = _xml_text(journal_elem, "Title") if journal_elem is not None else ""

        pubdate_elem = (
            journal_elem.find("JournalIssue/PubDate") if journal_elem is not None else None
        )
        date_str = None
        if pubdate_elem is not None:
            year = _xml_text(pubdate_elem, "Year")
            month_raw = _xml_text(pubdate_elem, "Month")
            day = _xml_text(pubdate_elem, "Day") or "01"
            if year.isdigit():
                month = "01"
                if month_raw:
                    if month_raw.isdigit():
                        month = f"{int(month_raw):02d}"
                    else:
                        mon_key = month_raw.lower()[:3]
                        if mon_key in _MONTH_TO_NUM:
                            month = f"{_MONTH_TO_NUM[mon_key]:02d}"
                day_num = int(day) if day.isdigit() else 1
                date_str = f"{year}-{month}-{day_num:02d}"

        # Authors: <AuthorList><Author><LastName>X</LastName><ForeName>Y</ForeName></Author>...
        author_list = []
        author_list_elem = article_elem.find("AuthorList")
        if author_list_elem is not None:
            for a in author_list_elem.findall("Author"):
                last = _xml_text(a, "LastName")
                fore = _xml_text(a, "ForeName")
                if last:
                    author_list.append(f"{last}, {fore}".strip(", "))

        first_author = author_list[0] if author_list else ""

        if not title:
            continue

        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        parsed.append({
            "id": pmid,
            "title": title.rstrip("."),
            "snippet": (abstract or title)[:500],
            "content": abstract,  # full abstract body — distinguishes efetch from esummary
            "url": url,
            "date": date_str,
            "source_domain": "pubmed.ncbi.nlm.nih.gov",
            "author": first_author,
            "relevance": 0.75,  # full-text gets a small bump over title-only
            "why_relevant": f"PubMed full abstract in {journal}" if journal else "PubMed full abstract",
            "metadata": {
                "pmid": pmid,
                "journal": journal,
                "first_author": first_author,
                "all_authors": author_list,
                "abstract_sections": len(abstract_parts),
            },
        })
    return parsed
