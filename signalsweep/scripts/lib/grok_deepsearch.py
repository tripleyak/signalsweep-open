"""Grok DeepSearch adapter (signalsweep 3.8+).

xAI Grok 4 with DeepSearch/DeeperSearch live-search mode. Strongest at
real-time / X-native signals + contrarian/adversarial framing.

Auth:
- Primary: `XAI_API_KEY` (Bearer)
- Fallback: `OPENROUTER_API_KEY` with `x-ai/grok-4`

Output: synthesis + citations. xAI returns citations as a flat URL list
at the response level (no titles); we extract the domain as title.

Cost: ~$1/query (estimate). DeepSearch is one of the cheapest deep-research
modes available.

Only runs when --deep-research + explicit --search=grok_deepsearch.
"""

from __future__ import annotations

import sys
from typing import Any
from urllib.parse import urlparse

from . import http

DIRECT_URL = "https://api.x.ai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

DIRECT_MODEL = "grok-4"
OPENROUTER_FALLBACK_MODEL = "x-ai/grok-4"

ESTIMATED_COST_USD = 1.00
DEFAULT_TIMEOUT_S = 300


def _log(msg: str) -> None:
    if sys.stderr.isatty():
        sys.stderr.write(f"[grok_deepsearch] {msg}\n")
        sys.stderr.flush()


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _build_prompt(topic: str, from_date: str, to_date: str) -> str:
    return (
        f"Conduct deep research on: {topic}\n"
        f"Date range: {from_date} to {to_date}\n"
        f"Use DeepSearch to surface real-time and X-native signals. Provide a "
        f"comprehensive synthesis with specific names, dates, numbers, and source "
        f"URLs. Surface contrarian viewpoints. Aim for analytical depth and "
        f"freshness over breadth."
    )


def _call_direct(
    topic: str,
    from_date: str,
    to_date: str,
    api_key: str,
) -> tuple[str, list[dict], str | None]:
    """Hit xAI chat completions with DeepSearch mode. Returns (synthesis, citations, error)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DIRECT_MODEL,
        "messages": [{"role": "user", "content": _build_prompt(topic, from_date, to_date)}],
        "search_parameters": {"mode": "on", "max_search_results": 50},
        "max_tokens": 16000,
    }
    try:
        data = http.post(DIRECT_URL, payload, headers=headers, timeout=DEFAULT_TIMEOUT_S)
    except http.HTTPError as e:
        if e.status_code in (401, 403):
            return "", [], "credentials_invalid"
        if e.status_code == 429:
            return "", [], "rate_limited"
        return "", [], f"http_{e.status_code}"
    except Exception as e:
        return "", [], f"network_error: {e}"

    choices = data.get("choices") or []
    if not choices:
        return "", [], "empty_response"

    synthesis = choices[0].get("message", {}).get("content") or ""

    # xAI-specific: citations is typically a flat list at response top level
    raw_citations = data.get("citations") or []
    citations: list[dict] = []
    seen_urls: set[str] = set()
    for entry in raw_citations:
        # Entries can be plain URL strings or {url, title} objects depending on API version
        if isinstance(entry, str):
            url = entry
            title = ""
        elif isinstance(entry, dict):
            url = entry.get("url", "")
            title = entry.get("title", "")
        else:
            continue
        if url and url not in seen_urls:
            seen_urls.add(url)
            citations.append({"url": url, "title": title or _domain(url)})

    return synthesis, citations, None


def _call_openrouter_fallback(
    topic: str,
    from_date: str,
    to_date: str,
    api_key: str,
    model: str = OPENROUTER_FALLBACK_MODEL,
) -> tuple[str, list[dict], str | None]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": _build_prompt(topic, from_date, to_date)}],
        "max_tokens": 16000,
    }
    try:
        data = http.post(OPENROUTER_URL, payload, headers=headers, timeout=DEFAULT_TIMEOUT_S)
    except http.HTTPError as e:
        if e.status_code in (401, 403):
            return "", [], "credentials_invalid"
        if e.status_code == 429:
            return "", [], "rate_limited"
        return "", [], f"http_{e.status_code}"
    except Exception as e:
        return "", [], f"network_error: {e}"

    choices = data.get("choices") or []
    if not choices:
        return "", [], "empty_response"

    msg = choices[0].get("message") or {}
    synthesis = msg.get("content") or ""
    annotations = msg.get("annotations") or []
    citations: list[dict] = []
    seen_urls: set[str] = set()
    for ann in annotations:
        ucitation = ann.get("url_citation") or {}
        url = ucitation.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            citations.append({"url": url, "title": ucitation.get("title", "") or _domain(url)})

    return synthesis, citations, None


def search_grok_deepsearch(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run Grok DeepSearch. Returns paid_api-style envelope."""
    config = config or {}
    direct_key = config.get("XAI_API_KEY") or ""
    fallback_key = config.get("OPENROUTER_API_KEY") or ""

    if not direct_key and not fallback_key:
        return {"items": None, "error": "credentials_missing"}

    _log(f"Querying for '{topic}' ({from_date} to {to_date})")

    synthesis = ""
    citations: list[dict] = []
    error: str | None = None
    used_route = "direct"

    if direct_key:
        synthesis, citations, error = _call_direct(topic, from_date, to_date, direct_key)
        if error in ("credentials_invalid", "rate_limited") and fallback_key:
            _log(f"Direct API {error}; falling back to OpenRouter")
            used_route = "openrouter"
            synthesis, citations, error = _call_openrouter_fallback(
                topic, from_date, to_date, fallback_key,
            )
    elif fallback_key:
        used_route = "openrouter"
        synthesis, citations, error = _call_openrouter_fallback(
            topic, from_date, to_date, fallback_key,
        )

    if error:
        return {"items": None, "error": error}
    if not synthesis:
        return {"items": None, "error": "empty_synthesis"}

    return {
        "items": {
            "synthesis": synthesis,
            "citations": citations,
            "route": used_route,
            "model": DIRECT_MODEL if used_route == "direct" else OPENROUTER_FALLBACK_MODEL,
        },
        "error": None,
    }


def parse_grok_deepsearch_response(response: dict[str, Any], query: str = "") -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    body = response["items"]
    if not isinstance(body, dict):
        return []

    synthesis = body.get("synthesis", "") or ""
    citations = body.get("citations", []) or []
    route = body.get("route", "direct")
    model = body.get("model", DIRECT_MODEL)

    if not synthesis:
        return []

    items: list[dict[str, Any]] = []

    items.append({
        "id": "GROK_DS1",
        "title": f"Grok DeepSearch: {query}" if query else "Grok DeepSearch synthesis",
        "snippet": synthesis[:500],
        "url": "",
        "source_domain": "x.ai" if route == "direct" else "openrouter.ai",
        "date": None,
        "relevance": 0.92,
        "why_relevant": f"Grok DeepSearch synthesis for '{query}'" if query else "Grok DeepSearch synthesis",
        "metadata": {
            "provider": "grok_deepsearch",
            "model": model,
            "route": route,
            "synthesis": synthesis,
            "synthesis_length": len(synthesis),
            "citation_count": len(citations),
            "estimated_cost_usd": ESTIMATED_COST_USD,
            "strengths": "real-time + X-native signals",
        },
    })

    for i, cit in enumerate(citations):
        url = cit.get("url", "")
        title = cit.get("title", "") or _domain(url)
        if not url:
            continue
        items.append({
            "id": f"GROK_DS{i + 2}",
            "title": title,
            "snippet": f"Cited in Grok DeepSearch synthesis for '{query}'",
            "url": url,
            "source_domain": _domain(url),
            "date": None,
            "relevance": 0.72,
            "why_relevant": f"Grok DeepSearch citation for '{query}'" if query else "Grok DeepSearch citation",
            "metadata": {"cited_in": "grok_deepsearch"},
        })

    return items
