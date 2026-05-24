"""Stack Overflow search via Stack Exchange API (free, no auth required).

Uses api.stackexchange.com for question discovery. Supports date filtering
and engagement metrics (score, answer_count, view_count).
No API key needed for basic usage (300 requests/day quota).
"""

import math
import sys
from typing import Any, Dict, List

from . import http
from .query import extract_core_subject
from .relevance import token_overlap_relevance

SE_SEARCH_URL = "https://api.stackexchange.com/2.3/search/advanced"

DEPTH_CONFIG = {
    "quick": 10,
    "default": 20,
    "deep": 40,
}


def _log(msg: str):
    if sys.stderr.isatty():
        sys.stderr.write(f"[SO] {msg}\n")
        sys.stderr.flush()


def _date_to_unix(date_str: str) -> int:
    import datetime
    parts = date_str.split("-")
    dt = datetime.datetime(int(parts[0]), int(parts[1]), int(parts[2]),
                           tzinfo=datetime.timezone.utc)
    return int(dt.timestamp())


def _unix_to_date(ts: int) -> str:
    import datetime
    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%d")


def search_stackoverflow(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
) -> Dict[str, Any]:
    """Search Stack Overflow via Stack Exchange API.

    Args:
        topic: Search topic
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'

    Returns:
        Dict with 'items' list from SE API.
    """
    count = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])
    from_ts = _date_to_unix(from_date)
    to_ts = _date_to_unix(to_date) + 86400

    core = extract_core_subject(topic)
    _log(f"Searching for '{core}' (raw: '{topic}', since {from_date}, count={count})")

    from urllib.parse import urlencode
    params = {
        "q": core,
        "fromdate": str(from_ts),
        "todate": str(to_ts),
        "order": "desc",
        "sort": "relevance",
        "site": "stackoverflow",
        "pagesize": str(min(count, 100)),
        "filter": "withbody",
    }

    url = f"{SE_SEARCH_URL}?{urlencode(params)}"

    try:
        response = http.request("GET", url, timeout=30)
    except Exception as e:
        _log(f"Search failed: {e}")
        return {"items": [], "error": str(e)}

    items = response.get("items", [])
    _log(f"Found {len(items)} questions")
    return response


def parse_stackoverflow_response(
    response: Dict[str, Any],
    query: str = "",
) -> List[Dict[str, Any]]:
    """Parse Stack Exchange response into normalized item dicts.

    Args:
        response: SE API response
        query: Original search query for relevance scoring

    Returns:
        List of item dicts ready for normalization.
    """
    items = response.get("items", [])
    parsed = []

    for i, item in enumerate(items):
        question_id = item.get("question_id", 0)
        so_score = item.get("score", 0)
        answer_count = item.get("answer_count", 0)
        view_count = item.get("view_count", 0)
        is_answered = item.get("is_answered", False)

        creation_date = item.get("creation_date")
        date_str = _unix_to_date(creation_date) if creation_date else None

        url = item.get("link", f"https://stackoverflow.com/q/{question_id}")
        title = item.get("title", "")
        tags = item.get("tags", [])
        owner = item.get("owner", {})
        author = owner.get("display_name", "") if isinstance(owner, dict) else ""

        # Body snippet (strip HTML)
        body = item.get("body", "")
        if body:
            import re
            body = re.sub(r'<[^>]+>', '', body)
            body = body[:300].strip()

        # Relevance scoring
        rank_score = max(0.3, 1.0 - (i * 0.03))
        engagement_boost = min(0.15, math.log1p(max(0, so_score)) / 30)
        if query:
            tag_text = " ".join(tags)
            content_score = token_overlap_relevance(query, f"{title} {tag_text}")
            relevance = min(1.0, 0.55 * rank_score + 0.45 * content_score + engagement_boost)
        else:
            relevance = min(1.0, rank_score * 0.7 + engagement_boost + 0.1)

        parsed.append({
            "question_id": question_id,
            "title": title,
            "url": url,
            "author": author,
            "tags": tags,
            "body_snippet": body,
            "is_answered": is_answered,
            "accepted_answer_id": item.get("accepted_answer_id"),
            "date": date_str,
            "engagement": {
                "score": so_score,
                "answer_count": answer_count,
                "view_count": view_count,
            },
            "relevance": round(relevance, 2),
            "why_relevant": f"SO question: {title[:60]}",
        })

    return parsed
