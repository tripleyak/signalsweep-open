"""OpenRouter generic deep-research adapter (signalsweep 3.8+).

A first-class source that targets any OpenRouter-hosted research-capable
model. Default model is `perplexity/sonar-deep-research` (continuity with
the existing v3.7 perplexity source). Override via `OPENROUTER_RESEARCH_MODEL`
env var to route to any OpenRouter model — e.g.,
`anthropic/claude-opus-4-6`, `openai/o1-pro`, `google/gemini-2.5-pro`,
`x-ai/grok-4`, etc.

Auth: `OPENROUTER_API_KEY` (Bearer).

Output shape: synthesis + citations matching the v3.8 provider contract.
Cost: depends on routed model; default Perplexity Sonar Deep Research
~$0.90/query.

Use cases:
- Quickly try a research model without writing a dedicated adapter
- Route around direct-provider rate limits
- Compare OpenRouter pricing/availability against direct provider APIs
- Single-billing convenience when user prefers OpenRouter over direct keys

Only runs when --deep-research + explicit --search=openrouter_research.
"""

from __future__ import annotations

import sys
from typing import Any
from urllib.parse import urlparse

from . import http

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "perplexity/sonar-deep-research"

ESTIMATED_COST_USD = 1.00  # rough average across common research models
DEFAULT_TIMEOUT_S = 600


def _log(msg: str) -> None:
    if sys.stderr.isatty():
        sys.stderr.write(f"[openrouter_research] {msg}\n")
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
        f"Provide a comprehensive synthesis with specific names, dates, numbers, "
        f"and inline source citations. Cover multiple perspectives. Aim for "
        f"analytical depth over breadth."
    )


def _resolve_model(config: dict[str, Any]) -> str:
    return (config.get("OPENROUTER_RESEARCH_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def search_openrouter_research(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run deep research via OpenRouter using any routable model."""
    config = config or {}
    api_key = config.get("OPENROUTER_API_KEY") or ""
    if not api_key:
        return {"items": None, "error": "credentials_missing"}

    model = _resolve_model(config)
    _log(f"Querying via OpenRouter ({model}) for '{topic}' ({from_date} to {to_date})")

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
            return {"items": None, "error": "credentials_invalid"}
        if e.status_code == 429:
            return {"items": None, "error": "rate_limited"}
        return {"items": None, "error": f"http_{e.status_code}"}
    except Exception as e:
        return {"items": None, "error": f"network_error: {e}"}

    choices = data.get("choices") or []
    if not choices:
        return {"items": None, "error": "empty_response"}

    msg = choices[0].get("message") or {}
    synthesis = msg.get("content") or ""
    if not synthesis:
        return {"items": None, "error": "empty_synthesis"}

    annotations = msg.get("annotations") or []
    citations: list[dict] = []
    seen_urls: set[str] = set()
    for ann in annotations:
        ucitation = ann.get("url_citation") or {}
        url = ucitation.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            citations.append({"url": url, "title": ucitation.get("title", "") or _domain(url)})

    return {
        "items": {
            "synthesis": synthesis,
            "citations": citations,
            "model": model,
        },
        "error": None,
    }


def parse_openrouter_research_response(response: dict[str, Any], query: str = "") -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    body = response["items"]
    if not isinstance(body, dict):
        return []

    synthesis = body.get("synthesis", "") or ""
    citations = body.get("citations", []) or []
    model = body.get("model", DEFAULT_MODEL)

    if not synthesis:
        return []

    items: list[dict[str, Any]] = []

    items.append({
        "id": "OR_R1",
        "title": f"OpenRouter Research ({model}): {query}" if query else f"OpenRouter Research ({model})",
        "snippet": synthesis[:500],
        "url": "",
        "source_domain": "openrouter.ai",
        "date": None,
        "relevance": 0.90,
        "why_relevant": f"OpenRouter ({model}) deep-research synthesis for '{query}'" if query else f"OpenRouter ({model}) synthesis",
        "metadata": {
            "provider": "openrouter_research",
            "model": model,
            "route": "openrouter",
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
            "id": f"OR_R{i + 2}",
            "title": title,
            "snippet": f"Cited in OpenRouter Research ({model}) synthesis for '{query}'",
            "url": url,
            "source_domain": _domain(url),
            "date": None,
            "relevance": 0.72,
            "why_relevant": f"OpenRouter Research citation for '{query}'" if query else "OpenRouter Research citation",
            "metadata": {"cited_in": "openrouter_research", "model": model},
        })

    return items
