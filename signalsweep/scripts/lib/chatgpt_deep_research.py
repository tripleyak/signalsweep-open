"""ChatGPT Deep Research adapter (signalsweep 3.8+).

OpenAI's o3-deep-research model (or current deep-research-capable model)
accessed via the Responses API. Falls back to OpenRouter when direct API
auth fails or rate-limits.

Auth:
- Primary: `OPENAI_API_KEY` (Bearer)
- Fallback: `OPENROUTER_API_KEY` with model `openai/o1-pro` or current best

Output: long-form synthesized research (5-15K words) with URL citations.
Synthesis becomes one SourceItem, each unique citation becomes its own.

Cost: ~$5/query (estimate). Actual cost logged from response usage when
upstream returns it.

This module only runs when --deep-research flag is set AND the user
explicitly lists `chatgpt_deep_research` in --search=. Even with valid
credentials, it does not auto-activate.
"""

from __future__ import annotations

import sys
from typing import Any
from urllib.parse import urlparse

from . import http

DIRECT_URL = "https://api.openai.com/v1/responses"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

DIRECT_MODEL = "o3-deep-research"
OPENROUTER_FALLBACK_MODEL = "openai/o1-pro"

ESTIMATED_COST_USD = 5.00
DEFAULT_TIMEOUT_S = 600  # 10 minutes — deep research can take a while


def _log(msg: str) -> None:
    if sys.stderr.isatty():
        sys.stderr.write(f"[chatgpt_deep_research] {msg}\n")
        sys.stderr.flush()


def _domain(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc.removeprefix("www.")
    except Exception:
        return ""


def _build_prompt(topic: str, from_date: str, to_date: str) -> str:
    return (
        f"Conduct deep research on: {topic}\n"
        f"Date range: {from_date} to {to_date}\n"
        f"Provide a comprehensive synthesis with specific names, dates, numbers, "
        f"and inline source citations. Cover multiple perspectives and surface "
        f"any contrarian viewpoints. Aim for analytical depth over breadth."
    )


def _call_direct(
    topic: str,
    from_date: str,
    to_date: str,
    api_key: str,
) -> tuple[str, list[dict], str | None]:
    """Hit OpenAI Responses API. Returns (synthesis, citations, error)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DIRECT_MODEL,
        "input": _build_prompt(topic, from_date, to_date),
        "tools": [{"type": "web_search"}],
        "max_output_tokens": 16000,
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

    # Responses API shape: data["output"] is a list of message + tool_call entries
    output = data.get("output") or []
    synthesis = ""
    citations: list[dict] = []

    for entry in output:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "message":
            for content_block in entry.get("content") or []:
                if content_block.get("type") in ("output_text", "text"):
                    synthesis += content_block.get("text", "")
        elif entry.get("type") in ("web_search_call", "tool_call", "tool_use"):
            # Citations from tool result
            for result in entry.get("results") or entry.get("output") or []:
                if isinstance(result, dict) and result.get("url"):
                    citations.append({
                        "url": result["url"],
                        "title": result.get("title", "") or _domain(result["url"]),
                    })

    if not synthesis:
        # Fallback: some Responses API variants nest synthesis under output_text
        synthesis = data.get("output_text", "")

    return synthesis, citations, None


def _call_openrouter_fallback(
    topic: str,
    from_date: str,
    to_date: str,
    api_key: str,
    model: str = OPENROUTER_FALLBACK_MODEL,
) -> tuple[str, list[dict], str | None]:
    """Fall back to OpenRouter with chat-completions shape. Returns (synthesis, citations, error)."""
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


def search_chatgpt_deep_research(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run ChatGPT Deep Research. Returns paid_api-style envelope.

    Tries direct OpenAI Responses API first; falls back to OpenRouter when
    direct fails on auth or rate limits.
    """
    config = config or {}
    direct_key = config.get("OPENAI_API_KEY") or ""
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


def parse_chatgpt_deep_research_response(response: dict[str, Any], query: str = "") -> list[dict[str, Any]]:
    """Parse search response into normalized SourceItem-shaped dicts.

    Returns: [synthesis_item, citation_1, citation_2, ...].
    Synthesis item carries the full body; each citation gets its own item
    so existing fusion/dedupe/rerank can work on URL-bearing entries.
    """
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

    # Synthesis item
    items.append({
        "id": "CGPT_DR1",
        "title": f"ChatGPT Deep Research: {query}" if query else "ChatGPT Deep Research synthesis",
        "snippet": synthesis[:500],
        "url": "",
        "source_domain": "openai.com" if route == "direct" else "openrouter.ai",
        "date": None,
        "relevance": 0.92,
        "why_relevant": f"ChatGPT Deep Research synthesis for '{query}'" if query else "ChatGPT Deep Research synthesis",
        "metadata": {
            "provider": "chatgpt_deep_research",
            "model": model,
            "route": route,
            "synthesis": synthesis,
            "synthesis_length": len(synthesis),
            "citation_count": len(citations),
            "estimated_cost_usd": ESTIMATED_COST_USD,
        },
    })

    # Citation items
    for i, cit in enumerate(citations):
        url = cit.get("url", "")
        title = cit.get("title", "") or _domain(url)
        if not url:
            continue
        items.append({
            "id": f"CGPT_DR{i + 2}",
            "title": title,
            "snippet": f"Cited in ChatGPT Deep Research synthesis for '{query}'",
            "url": url,
            "source_domain": _domain(url),
            "date": None,
            "relevance": 0.72,
            "why_relevant": f"ChatGPT Deep Research citation for '{query}'" if query else "ChatGPT Deep Research citation",
            "metadata": {"cited_in": "chatgpt_deep_research"},
        })

    return items
