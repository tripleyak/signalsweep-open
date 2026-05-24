"""Digg news-sitemap source for signalsweep.

Fetches Digg's Google News sitemap (digg.com/news-sitemap.xml) which contains
~500 recent curated AI/tech story clusters with titles, URLs, and publication
dates. Filters by topic relevance using token overlap.

Previous implementation shelled out to `digg-pp-cli` (a private, unpublished
CLI tool from the upstream last30days maintainer). This rewrite uses the public
news sitemap instead — no CLI dependency, no auth, always available.

Activation: always available when public APIs enabled (no CLI gate).
Gated by SIGNALSWEEP_DISABLE_PUBLIC_APIS (v3.6 public-data tier).
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from html import unescape

from . import public_api
from .relevance import token_overlap_relevance

SITEMAP_URL = "https://digg.com/news-sitemap.xml"

DEPTH_CONFIG = {
    "quick": 8,
    "default": 20,
    "deep": 40,
}

POLITE_SLEEP = 0.5

NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "news": "http://www.google.com/schemas/sitemap-news/0.9",
}


def search_digg(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Fetch and parse Digg news sitemap, return matching clusters."""
    config = config or {}
    if not public_api.is_public_apis_enabled(config):
        return {"results": [], "error": "public_apis_disabled"}

    if not topic or not topic.strip():
        return {"results": []}

    time.sleep(POLITE_SLEEP)

    result = public_api.fetch_xml(
        SITEMAP_URL,
        cache_key=f"digg_sitemap:{from_date}",
        user_agent_suffix="(digg-sitemap-adapter)",
    )

    if result.get("error") or not result.get("items"):
        return {"results": [], "error": result.get("error")}

    root = result["items"]
    entries = _parse_sitemap(root)

    if from_date:
        entries = [e for e in entries if not e.get("date") or e["date"] >= from_date]

    return {"results": entries}


def parse_digg_response(
    response: Dict[str, Any],
    query: str = "",
) -> List[Dict[str, Any]]:
    """Filter and score sitemap entries by topic relevance."""
    raw = response.get("results") if isinstance(response, dict) else None
    if not isinstance(raw, list):
        return []

    topic_lower = query.lower().strip() if query else ""
    scored = []

    for entry in raw:
        if not isinstance(entry, dict):
            continue
        title = entry.get("title") or ""
        if not title:
            continue

        if topic_lower:
            relevance = token_overlap_relevance(query, title)
            if relevance < 0.1:
                continue
        else:
            relevance = 0.5

        scored.append((relevance, entry))

    scored.sort(key=lambda x: -x[0])

    items: List[Dict[str, Any]] = []
    for i, (rel, entry) in enumerate(scored):
        cluster_url_id = entry.get("cluster_url_id") or ""
        title = entry.get("title") or ""
        url = entry.get("url") or ""
        date_str = entry.get("date")

        items.append({
            "id": cluster_url_id or f"digg_{i}",
            "title": title,
            "url": url,
            "tldr": "",
            "author": "",
            "date": date_str,
            "engagement": {
                "postCount": 0,
                "uniqueAuthors": 0,
                "rank": None,
                "rank_score": 0.0,
            },
            "first_post_age": None,
            "posts": [],
            "relevance": round(min(1.0, rel), 2),
            "why_relevant": f"Digg cluster: {title[:80]}",
        })

    return items


def _parse_sitemap(root: Any) -> List[Dict[str, Any]]:
    """Extract entries from a Google News sitemap XML root."""
    entries = []
    if root is None:
        return entries

    for url_elem in root.findall("sm:url", NS):
        loc = url_elem.findtext("sm:loc", default="", namespaces=NS).strip()
        if not loc:
            continue

        cluster_url_id = loc.rstrip("/").rsplit("/", 1)[-1] if "/" in loc else ""

        news_elem = url_elem.find("news:news", NS)
        title = ""
        pub_date = ""
        if news_elem is not None:
            title = unescape(news_elem.findtext("news:title", default="", namespaces=NS).strip())
            pub_date = news_elem.findtext("news:publication_date", default="", namespaces=NS).strip()

        lastmod = url_elem.findtext("sm:lastmod", default="", namespaces=NS).strip()

        date_str = ""
        raw_date = pub_date or lastmod
        if raw_date:
            date_str = raw_date[:10]

        if not title:
            continue

        entries.append({
            "cluster_url_id": cluster_url_id,
            "title": title,
            "url": loc,
            "date": date_str or None,
        })

    return entries


def fetch_top_posts(cluster_url_id: str, posts_per: int = 5) -> List[Dict[str, Any]]:
    """Stub — post enrichment not available via sitemap."""
    return []


def enrich_with_top_posts(
    items: List[Dict[str, Any]],
    top_k: int = 3,
    posts_per: int = 5,
) -> List[Dict[str, Any]]:
    """Stub — post enrichment not available via sitemap."""
    return items


def enrich_source_items(items: list, top_k: int = 3, posts_per: int = 5) -> list:
    """Stub — post enrichment not available via sitemap."""
    return items
