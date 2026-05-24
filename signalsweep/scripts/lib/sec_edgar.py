"""SEC EDGAR full-text search via efts.sec.gov/LATEST/search-index (signalsweep 3.6+).

No auth required, but SEC mandates a specific User-Agent format:
`<Organization or Name> <contact email>`. We honor this via a direct
User-Agent header override instead of the default signalsweep/3.6 UA.

Rate limit: 10 requests/second. Respected via public_api's 429 retry logic.
Response shape: ElasticSearch-style `{"hits": {"hits": [...], "total": {...}}}`.

Signalsweep configuration:
- Optional `SEC_EDGAR_CONTACT_EMAIL` in config — used as the contact email in
  the UA. Falls back to `contact@signalsweep.dev` when unset (users are
  encouraged to set their own so SEC can reach them for abuse reports).
"""

from __future__ import annotations

from typing import Any

from . import public_api


SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

DEPTH_LIMITS = {
    "quick": 10,
    "default": 25,
    "deep": 50,
}

DEPTH_FORMS = {
    "quick": "10-K,10-Q,8-K",
    "default": "10-K,10-Q,8-K,DEF 14A,13F-HR",
    "deep": "",  # empty = all forms
}


def _user_agent(config: dict[str, Any] | None) -> str:
    email = (config or {}).get("SEC_EDGAR_CONTACT_EMAIL") or "contact@signalsweep.dev"
    return f"Signalsweep Research {email}"


def search_sec_edgar(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search EDGAR filings matching topic within date range."""
    forms = DEPTH_FORMS.get(depth, DEPTH_FORMS["default"])
    params = {
        "q": topic,
        "dateRange": "custom",
        "startdt": from_date,
        "enddt": to_date,
    }
    if forms:
        params["forms"] = forms

    return public_api.fetch_json(
        SEARCH_URL,
        params=params,
        cache_key=f"sec_edgar:{topic}:{from_date}:{to_date}:{depth}",
        extra_headers={"User-Agent": _user_agent(config)},
    )


def _filing_url(cik: str, accession: str) -> str:
    """Build the filing index URL from CIK + accession number.

    Example: CIK '0001418121', adsh '0001185185-15-000457' →
    https://www.sec.gov/Archives/edgar/data/1418121/000118518515000457/0001185185-15-000457-index.htm
    """
    try:
        cik_int = int(cik.lstrip("0") or "0")
    except ValueError:
        cik_int = 0
    acc_clean = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{accession}-index.htm"


def _first_company_name(display_names: list[str] | None) -> str:
    """Extract the company name from display_names like 'Apple Inc.  (AAPL)  (CIK 0000320193)'."""
    if not display_names:
        return ""
    raw = display_names[0] or ""
    # Strip everything after the first "  (" (ticker/CIK suffix)
    idx = raw.find("  (")
    return (raw[:idx] if idx > 0 else raw).strip()


def parse_sec_edgar_response(response: dict[str, Any], query: str = "") -> list[dict[str, Any]]:
    """Parse EDGAR search-index response into list of normalized item dicts."""
    if response.get("error") or not response.get("items"):
        return []

    hits = response["items"].get("hits", {}).get("hits", [])
    parsed = []
    for hit in hits:
        src = hit.get("_source", {}) or {}
        form = src.get("form") or ""
        file_date = src.get("file_date") or ""
        accession = src.get("adsh") or ""
        ciks = src.get("ciks") or []
        cik = ciks[0] if ciks else ""
        company = _first_company_name(src.get("display_names"))
        file_type = src.get("file_type") or form

        if not accession or not cik:
            continue

        url = _filing_url(cik, accession)
        title = f"{company} — {form}" if company else form
        body = (
            f"{company} filed {form} on {file_date}. "
            f"Document type: {file_type}. Accession: {accession}. CIK: {cik}."
        )

        parsed.append({
            "item_id": accession,
            "source": "sec_edgar",
            "title": title,
            "body": body,
            "url": url,
            "author": company or None,
            "container": form,
            "published_at": file_date,
            "engagement": {},
            "relevance_hint": 0.6,
            "why_relevant": f"SEC {form} filing by {company}" if company else f"SEC {form} filing",
            "metadata": {
                "form": form,
                "cik": cik,
                "accession_number": accession,
                "company_name": company,
                "file_type": file_type,
                "all_display_names": src.get("display_names") or [],
            },
        })
    return parsed
