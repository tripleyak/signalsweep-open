"""Spotify podcast/episode search (signalsweep 3.28.0+).

Podcast and episode search via Spotify Web API. Complements Listen Notes +
Podchaser with Spotify-unique popularity and audience data.

Endpoint: https://api.spotify.com/v1/search?type=show,episode
Auth: SPOTIFY_CLIENT_ID + SPOTIFY_CLIENT_SECRET (client_credentials flow).

Gated by SIGNALSWEEP_DISABLE_PAID_APIS (v3.7 paid-APIs tier).
"""

from __future__ import annotations
import json
import urllib.parse
import urllib.request
from typing import Any
from . import paid_api

TOKEN_URL = "https://accounts.spotify.com/api/token"
SEARCH_URL = "https://api.spotify.com/v1/search"
DEPTH_LIMITS = {"quick": 5, "default": 12, "deep": 25}

_token_cache: dict[str, str] = {}


def _get_token(client_id: str, client_secret: str) -> str | None:
    cache_key = f"{client_id}:{client_secret}"
    if cache_key in _token_cache:
        return _token_cache[cache_key]
    import base64
    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, headers={
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/x-www-form-urlencoded",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            token = data.get("access_token")
            if token:
                _token_cache[cache_key] = token
            return token
    except Exception:
        return None


def search_spotify_podcasts(topic: str, from_date: str, to_date: str, depth: str = "default", config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    if not paid_api.is_paid_apis_enabled(config):
        return {"items": None, "error": "paid_apis_disabled"}
    client_id = (config.get("SPOTIFY_CLIENT_ID") or "").strip()
    client_secret = (config.get("SPOTIFY_CLIENT_SECRET") or "").strip()
    if not (client_id and client_secret):
        return {"items": None, "error": "credentials_missing"}
    token = _get_token(client_id, client_secret)
    if not token:
        return {"items": None, "error": "spotify_auth_failed"}
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    return paid_api.fetch_json(
        SEARCH_URL,
        auth=paid_api.AuthSpec(type="bearer", value=token),
        params={"q": topic, "type": "episode", "limit": limit, "market": "US"},
        cache_key=f"spotify_podcasts:{topic}:{depth}",
        user_agent_suffix="(spotify-podcasts-adapter)",
    )


def parse_spotify_podcasts_response(response: dict[str, Any], query: str = "", from_date: str = "", to_date: str = "", depth: str = "default") -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    payload = response["items"]
    if not isinstance(payload, dict):
        return []
    episodes_obj = payload.get("episodes") or {}
    episodes = episodes_obj.get("items") or [] if isinstance(episodes_obj, dict) else []
    if not isinstance(episodes, list):
        return []
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    parsed = []
    for i, ep in enumerate(episodes[:limit]):
        if not isinstance(ep, dict):
            continue
        ep_id = ep.get("id") or ""
        if not ep_id:
            continue
        name = (ep.get("name") or "").strip()
        if not name:
            continue
        description = (ep.get("description") or "").strip()
        show_name = ""
        show = ep.get("show") or {}
        if isinstance(show, dict):
            show_name = (show.get("name") or "").strip()
        release_date = (ep.get("release_date") or "").strip()
        duration_ms = ep.get("duration_ms") or 0
        duration_min = round(duration_ms / 60000) if duration_ms else 0
        url = (ep.get("external_urls") or {}).get("spotify") or f"https://open.spotify.com/episode/{ep_id}"
        snippet_parts = []
        if show_name:
            snippet_parts.append(f"Show: {show_name}")
        if duration_min:
            snippet_parts.append(f"{duration_min} min")
        if description:
            snippet_parts.append(description[:200])
        snippet = " · ".join(snippet_parts) or f"Spotify episode: {name}"
        parsed.append({
            "id": f"spotify_ep:{ep_id}",
            "title": name[:200],
            "snippet": snippet[:500],
            "url": url,
            "source_domain": "spotify.com",
            "date": release_date or None,
            "relevance": max(0.3, 0.75 - (i * 0.03)),
            "why_relevant": f"Spotify podcast for '{query[:40]}'" if query else name[:60],
            "metadata": {"episode_id": ep_id, "show_name": show_name, "duration_min": duration_min, "signal_type": "podcast"},
        })
    return parsed
