"""RSS blog search for Medium and Substack articles.

Uses Google's RSS feed proxy and direct Medium/Substack tag feeds to discover
recent articles. No API key required — uses public RSS/Atom feeds parsed
with stdlib xml.etree.ElementTree.
"""

import math
import re
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from . import http
from .query import extract_core_subject
from .relevance import token_overlap_relevance

DEPTH_CONFIG = {
    "quick": 10,
    "default": 20,
    "deep": 40,
}

# Atom namespace
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def _log(msg: str):
    if sys.stderr.isatty():
        sys.stderr.write(f"[RSS] {msg}\n")
        sys.stderr.flush()


def _strip_html(text: str) -> str:
    """Strip HTML tags from text."""
    return re.sub(r'<[^>]+>', '', text).strip()


def _parse_date(date_str: str) -> Optional[str]:
    """Try to parse various date formats to YYYY-MM-DD."""
    if not date_str:
        return None

    import datetime

    # ISO 8601
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            dt = datetime.datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # RFC 2822 (common in RSS)
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%d %b %Y %H:%M:%S %z"):
        try:
            dt = datetime.datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Last resort: extract YYYY-MM-DD if present
    match = re.search(r'(\d{4}-\d{2}-\d{2})', date_str)
    if match:
        return match.group(1)

    return None


def _fetch_rss(url: str, timeout: int = 15) -> str:
    """Fetch RSS feed as raw XML string."""
    import urllib.request
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; signalsweep/1.0)",
        "Accept": "application/rss+xml, application/xml, text/xml",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _parse_rss_xml(xml_str: str) -> List[Dict[str, Any]]:
    """Parse RSS/Atom XML into item dicts."""
    items = []
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return items

    # RSS 2.0 format
    for item in root.iter("item"):
        title = item.findtext("title", "")
        link = item.findtext("link", "")
        pub_date = item.findtext("pubDate", "")
        description = item.findtext("description", "")
        creator = item.findtext("{http://purl.org/dc/elements/1.1/}creator", "")
        categories = [c.text for c in item.findall("category") if c.text]

        items.append({
            "title": _strip_html(title),
            "url": link.strip(),
            "date_raw": pub_date,
            "description": _strip_html(description)[:500],
            "author": creator or "",
            "categories": categories,
        })

    # Atom format (Medium uses this)
    for entry in root.findall("atom:entry", ATOM_NS):
        title = entry.findtext("atom:title", "", ATOM_NS)
        link_elem = entry.find("atom:link[@rel='alternate']", ATOM_NS)
        if link_elem is None:
            link_elem = entry.find("atom:link", ATOM_NS)
        link = link_elem.get("href", "") if link_elem is not None else ""
        updated = entry.findtext("atom:updated", "", ATOM_NS)
        published = entry.findtext("atom:published", "", ATOM_NS)
        content = entry.findtext("atom:content", "", ATOM_NS)
        summary = entry.findtext("atom:summary", "", ATOM_NS)
        author_elem = entry.find("atom:author", ATOM_NS)
        author = ""
        if author_elem is not None:
            author = author_elem.findtext("atom:name", "", ATOM_NS)
        categories = [c.get("term", "") for c in entry.findall("atom:category", ATOM_NS) if c.get("term")]

        items.append({
            "title": _strip_html(title),
            "url": link.strip(),
            "date_raw": published or updated,
            "description": _strip_html(summary or content)[:500],
            "author": author,
            "categories": categories,
        })

    return items


def _fetch_medium_tag(tag: str, timeout: int = 15) -> List[Dict[str, Any]]:
    """Fetch Medium articles for a tag via RSS feed."""
    safe_tag = quote_plus(tag.lower().replace(" ", "-"))
    url = f"https://medium.com/feed/tag/{safe_tag}"
    try:
        xml_str = _fetch_rss(url, timeout=timeout)
        items = _parse_rss_xml(xml_str)
        for item in items:
            item["platform"] = "medium"
        return items
    except Exception as e:
        _log(f"Medium tag '{tag}' failed: {e}")
        return []


def _fetch_substack_search(topic: str, timeout: int = 15) -> List[Dict[str, Any]]:
    """Search Substack via their public search/feed endpoint."""
    safe_topic = quote_plus(topic)
    # Substack doesn't have a tag RSS feed, but many popular substacks have feeds.
    # Use the Substack reader search endpoint.
    url = f"https://substack.com/api/v1/post/search?query={safe_topic}&limit=20"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; signalsweep/1.0)",
            "Accept": "application/json",
        }
        response = http.request("GET", url, headers=headers, timeout=timeout)

        items = []
        posts = response if isinstance(response, list) else response.get("posts", response.get("results", []))
        for post in posts:
            title = post.get("title", "")
            subtitle = post.get("subtitle", "")
            slug = post.get("slug", "")
            pub_domain = post.get("publishedBylines", [{}])
            pub_name = ""
            if post.get("publication"):
                pub_name = post["publication"].get("name", "")
                subdomain = post["publication"].get("subdomain", "")
                url_base = f"https://{subdomain}.substack.com" if subdomain else ""
            else:
                url_base = post.get("canonical_url", "").rsplit("/", 1)[0] if post.get("canonical_url") else ""

            items.append({
                "title": title,
                "url": post.get("canonical_url", f"{url_base}/p/{slug}" if url_base else ""),
                "date_raw": post.get("post_date", post.get("published_at", "")),
                "description": subtitle or post.get("description", "")[:500],
                "author": pub_name or post.get("author", {}).get("name", ""),
                "categories": [],
                "platform": "substack",
            })
        return items
    except Exception as e:
        _log(f"Substack search failed: {e}")
        return []


def search_rss_blogs(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
) -> Dict[str, Any]:
    """Search Medium and Substack for recent articles.

    Args:
        topic: Search topic
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'

    Returns:
        Dict with 'articles' list.
    """
    core = extract_core_subject(topic)
    _log(f"Searching blogs for '{core}' (raw: '{topic}', since {from_date})")

    # Generate search terms: the core subject + individual significant words
    terms = [core]
    words = core.split()
    if len(words) > 2:
        terms.extend(w for w in words if len(w) > 3)

    all_articles = []

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        # Medium tag feeds (try core + significant words)
        for term in terms[:3]:
            futures.append(executor.submit(_fetch_medium_tag, term))
        # Substack search
        futures.append(executor.submit(_fetch_substack_search, core))

        for future in as_completed(futures):
            try:
                result = future.result(timeout=20)
                all_articles.extend(result)
            except Exception as e:
                _log(f"Feed fetch failed: {e}")

    _log(f"Found {len(all_articles)} total articles")
    return {"articles": all_articles}


def parse_rss_response(
    response: Dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
) -> List[Dict[str, Any]]:
    """Parse RSS blog response into normalized item dicts.

    Args:
        response: Blog search response
        query: Original search query for relevance scoring
        from_date: Start date for filtering
        to_date: End date for filtering

    Returns:
        List of item dicts ready for normalization.
    """
    articles = response.get("articles", [])
    parsed = []
    seen_urls = set()

    for i, article in enumerate(articles):
        url = article.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        title = article.get("title", "")
        if not title:
            continue

        # Parse date
        date_str = _parse_date(article.get("date_raw", ""))

        # Date filter
        if date_str and from_date and date_str < from_date:
            continue
        if date_str and to_date and date_str > to_date:
            continue

        # Determine platform
        platform = article.get("platform", "")
        if not platform:
            if "medium.com" in url:
                platform = "medium"
            elif "substack.com" in url or ".substack." in url:
                platform = "substack"
            else:
                platform = "blog"

        # Relevance scoring
        rank_score = max(0.3, 1.0 - (i * 0.02))
        if query:
            cats = " ".join(article.get("categories", []))
            content_score = token_overlap_relevance(query, f"{title} {cats}")
            relevance = min(1.0, 0.50 * rank_score + 0.50 * content_score)
        else:
            relevance = min(1.0, rank_score * 0.6 + 0.1)

        parsed.append({
            "title": title,
            "url": url,
            "author": article.get("author", ""),
            "platform": platform,
            "description": article.get("description", "")[:300],
            "categories": article.get("categories", []),
            "date": date_str,
            "relevance": round(relevance, 2),
            "why_relevant": f"{platform.title()} article: {title[:60]}",
        })

    return parsed
