"""LinkedIn search via ScrapeCreators API.

Searches LinkedIn posts by topic. Requires SCRAPECREATORS_API_KEY.
Falls back to web search if ScrapeCreators is unavailable.
"""

import math
import sys
from typing import Any, Dict, List, Optional

from . import http
from .query import extract_core_subject
from .relevance import token_overlap_relevance

SCRAPECREATORS_LINKEDIN_URL = "https://api.scrapecreators.com/v2/linkedin/search/posts"

DEPTH_CONFIG = {
    "quick": 10,
    "default": 20,
    "deep": 40,
}


def _log(msg: str):
    if sys.stderr.isatty():
        sys.stderr.write(f"[LI] {msg}\n")
        sys.stderr.flush()


def search_linkedin(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    api_key: str = "",
) -> Dict[str, Any]:
    """Search LinkedIn posts via ScrapeCreators API.

    Args:
        topic: Search topic
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'
        api_key: ScrapeCreators API key

    Returns:
        Dict with 'posts' list.
    """
    if not api_key:
        return {"posts": [], "error": "SCRAPECREATORS_API_KEY required for LinkedIn search"}

    count = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])
    core = extract_core_subject(topic)
    _log(f"Searching for '{core}' (raw: '{topic}', since {from_date}, count={count})")

    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }

    payload = {
        "query": core,
        "limit": count,
        "date_range": "past_month",
        "sort_by": "relevance",
    }

    try:
        response = http.post(SCRAPECREATORS_LINKEDIN_URL, payload, headers=headers, timeout=30)
    except Exception as e:
        _log(f"ScrapeCreators LinkedIn search failed: {e}")
        msg = str(e)
        if any(code in msg for code in ("402", "403", "429", "500", "502", "503")):
            msg = "ScrapeCreators unavailable — visit scrapecreators.com to check status"
        return {"posts": [], "error": msg}

    posts = response.get("data", response.get("posts", response.get("results", [])))
    if isinstance(posts, dict):
        posts = posts.get("posts", posts.get("results", []))
    if not isinstance(posts, list):
        posts = []

    _log(f"Found {len(posts)} posts")
    return {"posts": posts}


def parse_linkedin_response(
    response: Dict[str, Any],
    query: str = "",
) -> List[Dict[str, Any]]:
    """Parse LinkedIn response into normalized item dicts.

    Args:
        response: ScrapeCreators LinkedIn response
        query: Original search query for relevance scoring

    Returns:
        List of item dicts ready for normalization.
    """
    posts = response.get("posts", [])
    parsed = []

    for i, post in enumerate(posts):
        # ScrapeCreators can return different shapes — handle flexibly
        text = (post.get("text", "") or
                post.get("content", "") or
                post.get("commentary", "") or
                post.get("body", ""))
        url = (post.get("url", "") or
               post.get("post_url", "") or
               post.get("permalink", ""))
        author_name = (post.get("author_name", "") or
                       post.get("author", {}).get("name", "") if isinstance(post.get("author"), dict)
                       else post.get("author", ""))
        author_headline = (post.get("author_headline", "") or
                           post.get("author", {}).get("headline", "") if isinstance(post.get("author"), dict)
                           else "")
        likes = post.get("likes", post.get("num_likes", post.get("reactions_count", 0)))
        comments = post.get("comments", post.get("num_comments", post.get("comments_count", 0)))
        reposts = post.get("reposts", post.get("num_reposts", post.get("shares_count", 0)))

        # Parse date
        date_str = post.get("date", post.get("posted_at", post.get("created_at", "")))
        if date_str and len(date_str) >= 10:
            date_str = date_str[:10]  # YYYY-MM-DD
        else:
            date_str = None

        if not text and not url:
            continue

        # Relevance scoring
        rank_score = max(0.3, 1.0 - (i * 0.03))
        engagement_boost = min(0.15, math.log1p(likes or 0) / 25)
        if query:
            content_score = token_overlap_relevance(query, text[:200])
            relevance = min(1.0, 0.50 * rank_score + 0.50 * content_score + engagement_boost)
        else:
            relevance = min(1.0, rank_score * 0.6 + engagement_boost + 0.1)

        parsed.append({
            "text": text,
            "url": url,
            "author_name": author_name,
            "author_headline": author_headline,
            "date": date_str,
            "engagement": {
                "likes": likes or 0,
                "comments": comments or 0,
                "reposts": reposts or 0,
            },
            "relevance": round(relevance, 2),
            "why_relevant": f"LinkedIn post by {author_name[:30]}: {text[:50]}",
        })

    return parsed
