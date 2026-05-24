"""Podcast episode search via Taddy GraphQL API for /signalsweep.

Searches podcast episodes by keyword, extracting engagement metrics
(popularity rank) and optionally fetching transcripts.

Requires TADDY_USER_ID and TADDY_API_KEY in config.
Free tier: 500 requests/month (cached responses don't count).
API docs: https://taddy.org/developers
"""

import json
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import http
from .relevance import token_overlap_relevance as _compute_relevance

TADDY_API_URL = "https://api.taddy.org"
TADDY_MAX_WORDS = 8

# Common filler words to strip before truncating queries for Taddy.
_FILLER_WORDS = frozenset({
    "the", "a", "an", "for", "and", "or", "in", "on", "of",
    "with", "to", "how", "what", "best",
})


def _truncate_query(query: str) -> str:
    """Truncate a search query to TADDY_MAX_WORDS words.

    Strips common filler words first to preserve the most meaningful
    terms, then takes up to TADDY_MAX_WORDS remaining words.
    """
    words = query.split()
    if len(words) <= TADDY_MAX_WORDS:
        return query

    # Remove filler words, keeping order
    meaningful = [w for w in words if w.lower() not in _FILLER_WORDS]

    # If stripping fillers still leaves too many, take first N
    if len(meaningful) > TADDY_MAX_WORDS:
        meaningful = meaningful[:TADDY_MAX_WORDS]

    # Edge case: if ALL words were filler, fall back to first N original words
    if not meaningful:
        meaningful = words[:TADDY_MAX_WORDS]

    truncated = " ".join(meaningful)
    _log(f"Query truncated to {TADDY_MAX_WORDS} words: {truncated}")
    return truncated


DEPTH_CONFIG = {
    "quick":   {"limit": 10, "max_transcripts": 2},
    "default": {"limit": 20, "max_transcripts": 4},
    "deep":    {"limit": 40, "max_transcripts": 6},
}


def _log(msg: str):
    """Log to stderr (only in interactive terminals)."""
    if sys.stderr.isatty():
        sys.stderr.write(f"[Podcasts] {msg}\n")
        sys.stderr.flush()


def _taddy_headers(config: Dict[str, Any]) -> Dict[str, str]:
    """Build Taddy API request headers."""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": http.USER_AGENT,
        "X-USER-ID": str(config.get("TADDY_USER_ID", "")),
        "X-API-KEY": config.get("TADDY_API_KEY", ""),
    }


def _parse_date(epoch_ms: Any) -> Optional[str]:
    """Parse epoch milliseconds or seconds to YYYY-MM-DD."""
    if not epoch_ms:
        return None
    try:
        ts = int(epoch_ms)
        # If it looks like milliseconds (> year 2100 in seconds), convert
        if ts > 4102444800:
            ts = ts // 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError, OSError):
        pass
    # Try ISO string
    if isinstance(epoch_ms, str):
        try:
            dt = datetime.fromisoformat(epoch_ms.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass
        if len(epoch_ms) >= 10:
            return epoch_ms[:10]
    return None


def _format_duration(seconds: Any) -> str:
    """Format duration in seconds to human-readable string."""
    if not seconds:
        return ""
    try:
        s = int(seconds)
        if s < 60:
            return f"{s}s"
        m = s // 60
        if m < 60:
            return f"{m}m"
        h = m // 60
        rm = m % 60
        return f"{h}h{rm}m"
    except (ValueError, TypeError):
        return ""


def search_podcasts(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Search podcast episodes via Taddy GraphQL API.

    Args:
        topic: Search topic
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'
        config: Config dict (for Taddy credentials)

    Returns:
        Dict with 'items' list and optional 'error'.
    """
    config = config or {}
    user_id = config.get("TADDY_USER_ID")
    api_key = config.get("TADDY_API_KEY")

    if not user_id or not api_key:
        return {"items": [], "error": "No TADDY_USER_ID/TADDY_API_KEY configured"}

    depth_cfg = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])
    limit = depth_cfg["limit"]

    # Taddy API limits search terms to 8 words
    search_term = _truncate_query(topic)

    _log(f"Searching podcasts for '{search_term}' (depth={depth}, limit={limit})")

    # Convert date to epoch seconds for Taddy filter
    try:
        from_epoch = int(datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        from_epoch = int(time.time()) - 30 * 86400

    # Build GraphQL query
    query = """
    {
      search(
        term: "%s"
        filterForTypes: PODCASTEPISODE
        filterForPublishedAfter: %d
        sortBy: POPULARITY
        limitPerPage: %d
        page: 1
      ) {
        searchId
        podcastEpisodes {
          uuid
          name
          description
          audioUrl
          datePublished
          duration
          podcastSeries {
            uuid
            name
            description
          }
        }
      }
    }
    """ % (search_term.replace('"', '\\"'), from_epoch, min(limit, 25))

    try:
        import urllib.request
        req = urllib.request.Request(
            TADDY_API_URL,
            data=json.dumps({"query": query}).encode("utf-8"),
            headers=_taddy_headers(config),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        _log(f"Taddy API error: {e}")
        return {"items": [], "error": f"{type(e).__name__}: {e}"}

    # Check for GraphQL errors
    if "errors" in data:
        error_msg = data["errors"][0].get("message", "Unknown GraphQL error")
        _log(f"Taddy GraphQL error: {error_msg}")
        return {"items": [], "error": error_msg}

    search_data = data.get("data", {}).get("search", {})
    raw_episodes = search_data.get("podcastEpisodes") or []

    _log(f"Found {len(raw_episodes)} episodes")

    items = []
    for raw in raw_episodes:
        if not isinstance(raw, dict):
            continue

        episode_id = raw.get("uuid", "")
        title = raw.get("name", "")
        description = raw.get("description", "") or ""
        # Strip HTML tags from description
        import re
        description = re.sub(r'<[^>]+>', '', description).strip()
        description = description[:500]

        audio_url = raw.get("audioUrl", "")
        date_published = raw.get("datePublished")
        duration = raw.get("duration")
        duration_str = _format_duration(duration)

        # Podcast series info
        series = raw.get("podcastSeries") or {}
        podcast_name = series.get("name", "")

        date_str = _parse_date(date_published)

        # Relevance
        relevance_text = f"{title} {description} {podcast_name}"
        relevance = _compute_relevance(topic, relevance_text)

        # Hard date filter
        if date_str and date_str < from_date:
            continue
        if date_str and date_str > to_date:
            continue

        items.append({
            "episode_id": episode_id,
            "title": title,
            "description": description,
            "podcast_name": podcast_name,
            "audio_url": audio_url,
            "date": date_str,
            "duration": duration_str,
            "relevance": relevance,
            "why_relevant": f"Podcast: {podcast_name} — {title[:50]}" if podcast_name else f"Podcast: {title[:60]}",
        })

    _log(f"After date filter: {len(items)} episodes")

    # Sort by relevance (Taddy already sorts by popularity)
    items.sort(key=lambda x: x["relevance"], reverse=True)

    return {"items": items}


def fetch_transcript(
    episode_uuid: str,
    config: Dict[str, Any],
) -> Optional[str]:
    """Fetch transcript for a single episode.

    Returns transcript text or None if unavailable.
    """
    query = """
    {
      getEpisodeTranscript(uuid: "%s") {
        text
        speaker
      }
    }
    """ % episode_uuid

    try:
        import urllib.request
        req = urllib.request.Request(
            TADDY_API_URL,
            data=json.dumps({"query": query}).encode("utf-8"),
            headers=_taddy_headers(config),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception:
        return None

    segments = (data.get("data", {}).get("getEpisodeTranscript") or [])
    if not segments:
        return None

    # Combine transcript segments
    parts = []
    for seg in segments[:100]:  # Cap at 100 segments
        if isinstance(seg, dict) and seg.get("text"):
            speaker = seg.get("speaker", "")
            text = seg["text"]
            if speaker:
                parts.append(f"{speaker}: {text}")
            else:
                parts.append(text)

    if not parts:
        return None

    transcript = " ".join(parts)
    # Truncate to ~500 words
    words = transcript.split()
    if len(words) > 500:
        transcript = " ".join(words[:500]) + "..."

    return transcript


def search_and_enrich(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Full podcast search: find episodes, then fetch transcripts for top results.

    Args:
        topic: Search topic
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'
        config: Config dict

    Returns:
        Dict with 'items' list and optional 'error'.
    """
    config = config or {}
    result = search_podcasts(topic, from_date, to_date, depth=depth, config=config)
    items = result.get("items", [])

    if not items:
        return result

    # Fetch transcripts for top N episodes
    depth_cfg = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])
    max_transcripts = depth_cfg["max_transcripts"]

    fetched = 0
    for item in items[:max_transcripts]:
        episode_id = item.get("episode_id")
        if not episode_id:
            continue
        transcript = fetch_transcript(episode_id, config)
        if transcript:
            item["transcript_snippet"] = transcript
            fetched += 1

    if fetched:
        _log(f"Got transcripts for {fetched}/{min(len(items), max_transcripts)} episodes")

    return {"items": items, "error": result.get("error")}


def parse_podcast_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse podcast search response to normalized format.

    Returns:
        List of item dicts ready for normalization.
    """
    return response.get("items", [])
