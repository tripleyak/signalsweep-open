"""Product Hunt search via the GraphQL API. Requires PRODUCTHUNT_TOKEN for authentication.

Searches recent product launches by topic using the Product Hunt v2 GraphQL API.
"""

import math
import sys
from typing import Any, Dict, List

from . import http
from .query import extract_core_subject
from .relevance import token_overlap_relevance

# Product Hunt GraphQL endpoint (requires Bearer token)
PH_API_URL = "https://api.producthunt.com/v2/api/graphql"

DEPTH_CONFIG = {
    "quick": 10,
    "default": 20,
    "deep": 40,
}


def _log(msg: str):
    if sys.stderr.isatty():
        sys.stderr.write(f"[PH] {msg}\n")
        sys.stderr.flush()


def search_producthunt(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict = None,
) -> Dict[str, Any]:
    """Search Product Hunt for recent product launches.

    Uses the v2 GraphQL API with Bearer token authentication.

    Args:
        topic: Search topic
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'
        config: Config dict containing PRODUCTHUNT_TOKEN

    Returns:
        Dict with 'posts' list.
    """
    count = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])
    core = extract_core_subject(topic)
    _log(f"Searching for '{core}' (raw: '{topic}', since {from_date}, count={count})")

    query_gql = """
    query SearchPosts($query: String!, $first: Int!) {
        posts(order: NEWEST, search: $query, first: $first) {
            edges {
                node {
                    id
                    name
                    tagline
                    description
                    url
                    website
                    votesCount
                    commentsCount
                    reviewsCount
                    slug
                    createdAt
                    topics {
                        edges {
                            node {
                                name
                            }
                        }
                    }
                    makers {
                        name
                        username
                    }
                }
            }
        }
    }
    """

    # Try GraphQL API first
    try:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        # Add API key if available
        ph_token = (config or {}).get("PRODUCTHUNT_TOKEN")
        if ph_token:
            headers["Authorization"] = f"Bearer {ph_token}"

        payload = {
            "query": query_gql,
            "variables": {
                "query": core,
                "first": count,
            },
        }

        response = http.post(PH_API_URL, payload, headers=headers, timeout=30)
        posts = []
        edges = (response.get("data", {}).get("posts", {}).get("edges", []))
        for edge in edges:
            node = edge.get("node", {})
            if node:
                posts.append(node)

        if posts:
            _log(f"Found {len(posts)} products via GraphQL")
            return {"posts": posts, "source": "graphql"}
    except Exception as e:
        _log(f"GraphQL search failed: {e}")

    return {"posts": [], "error": "Product Hunt API unavailable (check PRODUCTHUNT_TOKEN)"}


def parse_producthunt_response(
    response: Dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
) -> List[Dict[str, Any]]:
    """Parse Product Hunt response into normalized item dicts.

    Args:
        response: PH API response
        query: Original search query for relevance scoring
        from_date: Start date for filtering
        to_date: End date for filtering

    Returns:
        List of item dicts ready for normalization.
    """
    posts = response.get("posts", [])
    parsed = []
    source = response.get("source", "graphql")

    for i, post in enumerate(posts):
        if source == "graphql":
            name = post.get("name", "")
            tagline = post.get("tagline", "")
            description = post.get("description", "")
            slug = post.get("slug", "")
            url = f"https://www.producthunt.com/posts/{slug}" if slug else post.get("url", "")
            website = post.get("website", "")
            votes = post.get("votesCount", 0)
            comments = post.get("commentsCount", 0)
            reviews = post.get("reviewsCount", 0)
            created_at = post.get("createdAt", "")

            # Extract topics
            topics = []
            topic_edges = post.get("topics", {}).get("edges", [])
            for te in topic_edges:
                tn = te.get("node", {}).get("name", "")
                if tn:
                    topics.append(tn)

            # Extract makers
            makers = post.get("makers", [])
            maker_name = makers[0].get("name", "") if makers else ""

            # Parse date
            date_str = None
            if created_at:
                date_str = created_at[:10]  # YYYY-MM-DD from ISO
        else:
            # Web search fallback format
            name = post.get("name", post.get("title", ""))
            tagline = post.get("tagline", post.get("short_description", ""))
            description = post.get("description", "")
            slug = post.get("slug", "")
            url = f"https://www.producthunt.com/posts/{slug}" if slug else post.get("url", "")
            website = post.get("website", post.get("product_links", [{}])[0].get("url", "") if post.get("product_links") else "")
            votes = post.get("votesCount", post.get("votes_count", 0))
            comments = post.get("commentsCount", post.get("comments_count", 0))
            reviews = 0
            topics = []
            maker_name = ""
            date_str = post.get("day", post.get("created_at", ""))[:10] if post.get("day") or post.get("created_at") else None

        # Date filter
        if date_str and from_date and date_str < from_date:
            continue
        if date_str and to_date and date_str > to_date:
            continue

        # Relevance scoring
        rank_score = max(0.3, 1.0 - (i * 0.03))
        engagement_boost = min(0.15, math.log1p(votes) / 30)
        if query:
            content_score = token_overlap_relevance(query, f"{name} {tagline} {' '.join(topics)}")
            relevance = min(1.0, 0.55 * rank_score + 0.45 * content_score + engagement_boost)
        else:
            relevance = min(1.0, rank_score * 0.7 + engagement_boost + 0.1)

        parsed.append({
            "name": name,
            "tagline": tagline,
            "description": description[:300] if description else "",
            "url": url,
            "website": website,
            "maker": maker_name,
            "topics": topics,
            "date": date_str,
            "engagement": {
                "votes": votes,
                "comments": comments,
                "reviews": reviews,
            },
            "relevance": round(relevance, 2),
            "why_relevant": f"Product launch: {name} — {tagline[:60]}",
        })

    return parsed
