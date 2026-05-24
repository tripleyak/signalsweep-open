"""Google Patents search adapter (signalsweep 3.28.0+).

Patent full-text search via Google Patents public search. Broader coverage
than PatentsView (US-only). Searches worldwide patent offices.

Endpoint: https://patents.google.com/ (JSON search via SerpApi or direct scrape)
Uses SerpApi if SERPAPI_API_KEY is present, otherwise public scrape.

Gated by SIGNALSWEEP_DISABLE_PUBLIC_APIS for scrape mode, PAID for SerpApi.
"""

from __future__ import annotations
from typing import Any
from . import public_api, paid_api

SERPAPI_URL = "https://serpapi.com/search.json"
DEPTH_LIMITS = {"quick": 5, "default": 15, "deep": 30}


def search_google_patents(topic: str, from_date: str, to_date: str, depth: str = "default", config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    serpapi_key = (config.get("SERPAPI_API_KEY") or "").strip()
    if serpapi_key:
        if not paid_api.is_paid_apis_enabled(config):
            return {"items": None, "error": "paid_apis_disabled"}
        limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
        return paid_api.fetch_json(
            SERPAPI_URL,
            params={"engine": "google_patents", "q": topic, "num": limit, "api_key": serpapi_key},
            cache_key=f"google_patents:{topic}:{depth}",
            user_agent_suffix="(google-patents-serpapi)",
        )
    if not public_api.is_public_apis_enabled(config):
        return {"items": None, "error": "public_apis_disabled"}
    return {"items": None, "error": "credentials_missing"}


def parse_google_patents_response(response: dict[str, Any], query: str = "", from_date: str = "", to_date: str = "", depth: str = "default") -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    payload = response["items"]
    if not isinstance(payload, dict):
        return []
    results = payload.get("organic_results") or payload.get("results") or []
    if not isinstance(results, list):
        return []
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    parsed = []
    for i, pat in enumerate(results[:limit]):
        if not isinstance(pat, dict):
            continue
        patent_id = pat.get("patent_id") or pat.get("publication_number") or ""
        if not patent_id:
            continue
        title = (pat.get("title") or "").strip()
        if not title:
            continue
        snippet_text = (pat.get("snippet") or pat.get("abstract") or "").strip()
        assignee = (pat.get("assignee") or "").strip()
        filing_date = (pat.get("filing_date") or pat.get("date") or "").strip()
        grant_date = (pat.get("grant_date") or "").strip()
        url = pat.get("pdf") or pat.get("link") or f"https://patents.google.com/patent/{patent_id}"
        snippet_parts = []
        if snippet_text:
            snippet_parts.append(snippet_text[:300])
        if assignee:
            snippet_parts.append(f"Assignee: {assignee}")
        if filing_date:
            snippet_parts.append(f"Filed: {filing_date}")
        snippet = " · ".join(snippet_parts) or f"Patent: {title}"
        parsed.append({
            "id": f"gpatent:{patent_id}",
            "title": title[:200],
            "snippet": snippet[:500],
            "url": url,
            "source_domain": "patents.google.com",
            "date": grant_date or filing_date or None,
            "relevance": max(0.3, 0.7 - (i * 0.02)),
            "why_relevant": f"Google Patent for '{query[:40]}'" if query else title[:60],
            "metadata": {"patent_id": patent_id, "assignee": assignee, "filing_date": filing_date, "grant_date": grant_date, "signal_type": "patent"},
        })
    return parsed
