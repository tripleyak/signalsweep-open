"""Claude Research adapter (signalsweep 3.8+).

Anthropic Messages API with extended-thinking + web_search tool. This is
the API equivalent of Claude.ai's "Research" mode product feature.

Auth:
- Primary: `ANTHROPIC_API_KEY` (x-api-key header)
- Fallback: `OPENROUTER_API_KEY` with `anthropic/claude-opus-4-6`

Output: long-form synthesis with web citations from tool_result blocks.
Synthesis becomes one SourceItem; each unique cited URL becomes its own.

Cost: ~$3/query (estimate). Extended thinking budget 32K tokens + web
search adds up.

Only runs when --deep-research flag set AND `claude_research` is in --search=.
"""

from __future__ import annotations

import sys
from typing import Any
from urllib.parse import urlparse

from . import http

DIRECT_URL = "https://api.anthropic.com/v1/messages"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

DIRECT_MODEL = "claude-opus-4-6"
OPENROUTER_FALLBACK_MODEL = "anthropic/claude-opus-4-6"
ANTHROPIC_VERSION = "2023-06-01"
WEB_SEARCH_TOOL_TYPE = "web_search_20250305"

ESTIMATED_COST_USD = 3.00
DEFAULT_TIMEOUT_S = 600


def _log(msg: str) -> None:
    if sys.stderr.isatty():
        sys.stderr.write(f"[claude_research] {msg}\n")
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
        f"Use the web search tool extensively. Provide a comprehensive synthesis "
        f"with specific names, dates, numbers, and inline source citations. "
        f"Cover multiple perspectives and surface contrarian viewpoints. "
        f"Aim for analytical depth over breadth."
    )


def _call_direct(
    topic: str,
    from_date: str,
    to_date: str,
    api_key: str,
) -> tuple[str, list[dict], str | None]:
    """Hit Anthropic Messages API. Returns (synthesis, citations, error)."""
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "Content-Type": "application/json",
    }
    payload = {
        "model": DIRECT_MODEL,
        "max_tokens": 16000,
        "thinking": {"type": "enabled", "budget_tokens": 32000},
        "tools": [{"type": WEB_SEARCH_TOOL_TYPE, "name": "web_search"}],
        "messages": [{"role": "user", "content": _build_prompt(topic, from_date, to_date)}],
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

    # Anthropic response: data["content"] is a list of typed blocks
    content = data.get("content") or []
    synthesis = ""
    citations: list[dict] = []
    seen_urls: set[str] = set()

    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            synthesis += block.get("text", "")
        elif btype == "tool_result":
            # Web search results inside tool_result
            for entry in block.get("content") or []:
                if isinstance(entry, dict):
                    url = entry.get("url", "")
                    title = entry.get("title", "")
                elif isinstance(entry, str):
                    continue
                else:
                    continue
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    citations.append({"url": url, "title": title or _domain(url)})
        # Skip thinking blocks — they're internal reasoning, not synthesis

    return synthesis, citations, None


def _call_openrouter_fallback(
    topic: str,
    from_date: str,
    to_date: str,
    api_key: str,
    model: str = OPENROUTER_FALLBACK_MODEL,
) -> tuple[str, list[dict], str | None]:
    """Fall back to OpenRouter chat completions."""
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


def search_claude_research(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run Claude Research. Returns paid_api-style envelope."""
    config = config or {}
    direct_key = config.get("ANTHROPIC_API_KEY") or ""
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


def parse_claude_research_response(response: dict[str, Any], query: str = "") -> list[dict[str, Any]]:
    """Parse search response into normalized items."""
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
        "id": "CLAUDE_R1",
        "title": f"Claude Research: {query}" if query else "Claude Research synthesis",
        "snippet": synthesis[:500],
        "url": "",
        "source_domain": "anthropic.com" if route == "direct" else "openrouter.ai",
        "date": None,
        "relevance": 0.92,
        "why_relevant": f"Claude Research synthesis for '{query}'" if query else "Claude Research synthesis",
        "metadata": {
            "provider": "claude_research",
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
            "id": f"CLAUDE_R{i + 2}",
            "title": title,
            "snippet": f"Cited in Claude Research synthesis for '{query}'",
            "url": url,
            "source_domain": _domain(url),
            "date": None,
            "relevance": 0.72,
            "why_relevant": f"Claude Research citation for '{query}'" if query else "Claude Research citation",
            "metadata": {"cited_in": "claude_research"},
        })

    return items
