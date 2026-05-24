"""Gemini Deep Research adapter (signalsweep 3.8+).

Google Gemini 2.5 Pro with `googleSearch` grounding tool. This is the API
equivalent of the Gemini app's "Deep Research" product feature.

Auth:
- Primary: `GEMINI_API_KEY` / `GOOGLE_API_KEY` / `GOOGLE_GENAI_API_KEY`
  (any one) — query-param `?key=`
- Fallback: `OPENROUTER_API_KEY` with `google/gemini-2.5-pro`

Output: long-form synthesis with grounding metadata containing source URIs.
Synthesis becomes one SourceItem; each grounding chunk URI becomes its own.

Cost: ~$2/query (estimate). Gemini's pricing is per-token; deep-research
queries with grounding tend to consume larger input contexts.

Only runs when --deep-research + explicit --search=gemini_deep_research.
"""

from __future__ import annotations

import sys
from typing import Any
from urllib.parse import urlparse, urlencode

from . import http

DIRECT_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

DIRECT_MODEL = "gemini-2.5-pro"
OPENROUTER_FALLBACK_MODEL = "google/gemini-2.5-pro"

ESTIMATED_COST_USD = 2.00
DEFAULT_TIMEOUT_S = 300  # Gemini tends to be faster than OpenAI/Anthropic deep research


def _log(msg: str) -> None:
    if sys.stderr.isatty():
        sys.stderr.write(f"[gemini_deep_research] {msg}\n")
        sys.stderr.flush()


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _resolve_google_key(config: dict[str, Any]) -> str:
    """Pick first available Google-family API key (mirrors providers.py convention)."""
    return (
        config.get("GEMINI_API_KEY")
        or config.get("GOOGLE_API_KEY")
        or config.get("GOOGLE_GENAI_API_KEY")
        or ""
    )


def _build_prompt(topic: str, from_date: str, to_date: str) -> str:
    return (
        f"Conduct deep research on: {topic}\n"
        f"Date range: {from_date} to {to_date}\n"
        f"Use Google Search grounding extensively. Provide a comprehensive synthesis "
        f"with specific names, dates, numbers, and source citations. Cover multiple "
        f"perspectives. Aim for analytical depth over breadth."
    )


def _call_direct(
    topic: str,
    from_date: str,
    to_date: str,
    api_key: str,
) -> tuple[str, list[dict], str | None]:
    """Hit Gemini generateContent. Returns (synthesis, citations, error)."""
    url = DIRECT_URL_TEMPLATE.format(model=DIRECT_MODEL) + "?" + urlencode({"key": api_key})
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": _build_prompt(topic, from_date, to_date)}]}],
        "tools": [{"googleSearch": {}}],
        "generationConfig": {
            "thinkingConfig": {"includeThoughts": False},
            "maxOutputTokens": 16000,
        },
    }
    try:
        data = http.post(url, payload, headers=headers, timeout=DEFAULT_TIMEOUT_S)
    except http.HTTPError as e:
        if e.status_code in (401, 403):
            return "", [], "credentials_invalid"
        if e.status_code == 429:
            return "", [], "rate_limited"
        return "", [], f"http_{e.status_code}"
    except Exception as e:
        return "", [], f"network_error: {e}"

    candidates = data.get("candidates") or []
    if not candidates:
        return "", [], "empty_response"

    candidate = candidates[0]
    content = candidate.get("content") or {}
    parts = content.get("parts") or []
    synthesis = ""
    for part in parts:
        if isinstance(part, dict) and part.get("text"):
            # Skip parts marked as thoughts; only use surfaced text
            if part.get("thought"):
                continue
            synthesis += part["text"]

    # Grounding metadata: groundingChunks contain {web: {uri, title}}
    grounding_metadata = candidate.get("groundingMetadata") or {}
    grounding_chunks = grounding_metadata.get("groundingChunks") or []
    citations: list[dict] = []
    seen_urls: set[str] = set()
    for chunk in grounding_chunks:
        web = chunk.get("web") if isinstance(chunk, dict) else None
        if not web:
            continue
        url_str = web.get("uri", "")
        title = web.get("title", "")
        if url_str and url_str not in seen_urls:
            seen_urls.add(url_str)
            citations.append({"url": url_str, "title": title or _domain(url_str)})

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
        url_str = ucitation.get("url", "")
        if url_str and url_str not in seen_urls:
            seen_urls.add(url_str)
            citations.append({"url": url_str, "title": ucitation.get("title", "") or _domain(url_str)})

    return synthesis, citations, None


def search_gemini_deep_research(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run Gemini Deep Research. Returns paid_api-style envelope."""
    config = config or {}
    direct_key = _resolve_google_key(config)
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


def parse_gemini_deep_research_response(response: dict[str, Any], query: str = "") -> list[dict[str, Any]]:
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
        "id": "GEM_DR1",
        "title": f"Gemini Deep Research: {query}" if query else "Gemini Deep Research synthesis",
        "snippet": synthesis[:500],
        "url": "",
        "source_domain": "google.com" if route == "direct" else "openrouter.ai",
        "date": None,
        "relevance": 0.92,
        "why_relevant": f"Gemini Deep Research synthesis for '{query}'" if query else "Gemini Deep Research synthesis",
        "metadata": {
            "provider": "gemini_deep_research",
            "model": model,
            "route": route,
            "synthesis": synthesis,
            "synthesis_length": len(synthesis),
            "citation_count": len(citations),
            "estimated_cost_usd": ESTIMATED_COST_USD,
        },
    })

    for i, cit in enumerate(citations):
        url = cit.get("url", "")
        title = cit.get("title", "") or _domain(url)
        if not url:
            continue
        items.append({
            "id": f"GEM_DR{i + 2}",
            "title": title,
            "snippet": f"Cited in Gemini Deep Research synthesis for '{query}'",
            "url": url,
            "source_domain": _domain(url),
            "date": None,
            "relevance": 0.72,
            "why_relevant": f"Gemini Deep Research citation for '{query}'" if query else "Gemini Deep Research citation",
            "metadata": {"cited_in": "gemini_deep_research"},
        })

    return items
