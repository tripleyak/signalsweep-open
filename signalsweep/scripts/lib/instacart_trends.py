"""Instacart Trends editorial scrape adapter (signalsweep 3.26+).

Instacart publishes trend reports as blog posts at
https://www.instacart.com/company/data-trends/. There is no structured API.

The adapter fetches the trends page HTML, extracts article links/titles/snippets
via regex (no BeautifulSoup — minimal deps), and filters by topic relevance.

Tier: v3.6 `SIGNALSWEEP_DISABLE_PUBLIC_APIS`. No credentials required.

Graceful degradation: returns [] (not error) on unrecognizable HTML. The page
structure WILL change; loose matching patterns are intentional.
"""

from __future__ import annotations

import re
from typing import Any

from . import public_api


TRENDS_URL = "https://www.instacart.com/company/data-trends/"

DEPTH_LIMITS = {"quick": 3, "default": 10, "deep": 20}


def _extract_articles(html: str) -> list[dict[str, Any]]:
    """Extract articles from the trends page HTML using loose regex patterns.

    Returns a list of dicts with keys: title, url, snippet, date.
    Returns [] if the HTML structure is unrecognizable — never raises.
    """
    articles: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    # Strategy 1: Look for <a> tags linking to data-trends sub-pages with text.
    # Instacart blog links typically look like:
    #   <a href="/company/data-trends/some-article-slug">Article Title</a>
    # or full URLs:
    #   <a href="https://www.instacart.com/company/data-trends/...">...</a>
    link_pattern = re.compile(
        r'<a[^>]+href=["\']'
        r'((?:https?://(?:www\.)?instacart\.com)?/company/data-trends/[a-z0-9][a-z0-9\-/]*)'
        r'["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )

    for match in link_pattern.finditer(html):
        raw_url = match.group(1).strip()
        raw_title = match.group(2).strip()

        # Skip the index page itself
        cleaned_path = raw_url.rstrip("/")
        if cleaned_path.endswith("/data-trends") or cleaned_path == "/company/data-trends":
            continue

        # Normalize URL
        if raw_url.startswith("/"):
            url = f"https://www.instacart.com{raw_url}"
        else:
            url = raw_url
        url = url.rstrip("/")

        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Strip HTML tags from title
        title = re.sub(r"<[^>]+>", "", raw_title).strip()
        if not title or len(title) < 3:
            continue

        articles.append({
            "title": title[:200],
            "url": url,
            "snippet": "",
            "date": None,
        })

    # Strategy 2: Try to extract snippets from surrounding context.
    # Look for paragraph text near each article link.
    for article in articles:
        escaped_title = re.escape(article["title"][:50])
        # Look for a <p> or descriptive text near the title
        snippet_pattern = re.compile(
            escaped_title + r'.*?</a>.*?<p[^>]*>(.*?)</p>',
            re.IGNORECASE | re.DOTALL,
        )
        snippet_match = snippet_pattern.search(html)
        if snippet_match:
            snippet_text = re.sub(r"<[^>]+>", "", snippet_match.group(1)).strip()
            article["snippet"] = snippet_text[:300]

    # Strategy 3: Try to extract dates from nearby context.
    # Common patterns: "January 15, 2026", "Jan 15, 2026", "2026-01-15"
    date_iso_pattern = re.compile(r"(\d{4}-\d{2}-\d{2})")
    date_text_pattern = re.compile(
        r"((?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+\d{1,2},?\s+\d{4})",
        re.IGNORECASE,
    )

    for article in articles:
        if article["date"]:
            continue
        escaped_url = re.escape(article["url"].split("/")[-1][:30])
        # Look for dates near the article reference
        context_pattern = re.compile(
            escaped_url + r'.{0,500}',
            re.IGNORECASE | re.DOTALL,
        )
        context_match = context_pattern.search(html)
        if context_match:
            context = context_match.group(0)
            iso_match = date_iso_pattern.search(context)
            if iso_match:
                article["date"] = iso_match.group(1)
            else:
                text_match = date_text_pattern.search(context)
                if text_match:
                    article["date"] = _normalize_date(text_match.group(1))

    return articles


def _normalize_date(date_str: str) -> str | None:
    """Best-effort date normalization to YYYY-MM-DD. Returns None on failure."""
    import datetime

    for fmt in (
        "%B %d, %Y", "%B %d %Y",
        "%b %d, %Y", "%b %d %Y",
    ):
        try:
            dt = datetime.datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _topic_matches(topic: str, title: str, snippet: str) -> bool:
    """Check if any topic term appears in the title or snippet (case-insensitive)."""
    topic_lower = topic.lower()
    combined = f"{title} {snippet}".lower()

    # Check full topic phrase
    if topic_lower in combined:
        return True

    # Check individual words (skip short common words)
    words = [w for w in topic_lower.split() if len(w) > 2]
    if not words:
        return True  # trivial topic — match everything

    return any(w in combined for w in words)


def search_instacart_trends(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch the Instacart trends page and return raw HTML in an envelope.

    Returns {"items": {"html": <str>}, "error": None} on success,
    {"items": None, "error": "public_apis_disabled"} when disabled.
    """
    config = config or {}
    if not public_api.is_public_apis_enabled(config):
        return {"items": None, "error": "public_apis_disabled"}

    raw = public_api._fetch_raw(
        TRENDS_URL,
        params=None,
        cache_key=f"instacart_trends:{topic}:{depth}",
        cache_ttl_hours=public_api.DEFAULT_CACHE_TTL_HOURS,
        user_agent_suffix="(instacart_trends-adapter)",
        extra_headers={"Accept": "text/html,application/xhtml+xml"},
        timeout=public_api.DEFAULT_TIMEOUT_SECONDS,
    )

    if raw.get("error"):
        return {"items": None, "error": raw["error"]}

    body = raw.get("body") or b""
    try:
        html = body.decode("utf-8", errors="replace")
    except Exception:
        return {"items": None, "error": "parse_error"}

    return {"items": {"html": html, "topic": topic}, "error": None}


def parse_instacart_trends_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    """Parse Instacart trends HTML into normalized items.

    Returns [] on any parsing failure — never raises.
    """
    if response.get("error") or not response.get("items"):
        return []

    payload = response["items"]
    if not isinstance(payload, dict):
        return []

    html = payload.get("html") or ""
    topic = payload.get("topic") or query or ""
    if not html:
        return []

    try:
        articles = _extract_articles(html)
    except Exception:
        # Graceful degradation — never crash on unexpected HTML
        return []

    if not articles:
        return []

    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    # Filter by topic relevance if a topic is provided
    if topic:
        articles = [a for a in articles if _topic_matches(topic, a["title"], a["snippet"])]

    parsed = []
    for i, article in enumerate(articles[:limit]):
        parsed.append({
            "id": f"instacart_trends:{article['url'].split('/')[-1] or f'article_{i}'}",
            "title": article["title"],
            "snippet": article["snippet"] or f"Instacart trend report: {article['title'][:100]}",
            "url": article["url"],
            "source_domain": "instacart.com",
            "date": article.get("date"),
            "relevance": max(0.3, 0.7 - (i * 0.03)),
            "why_relevant": f"Instacart grocery trend: {article['title'][:60]}",
            "metadata": {
                "signal_type": "editorial",
                "data_type": "grocery_trend",
            },
        })

    return parsed
