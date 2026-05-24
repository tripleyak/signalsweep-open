"""Docker Hub image search (signalsweep 3.21.0+).

Endpoint: `hub.docker.com/v2/search/repositories/?query=X`. No auth.
v3.6 public-APIs tier.
"""

from __future__ import annotations

from typing import Any

from . import public_api

ENDPOINT = "https://hub.docker.com/v2/search/repositories/"
DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_docker_hub(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not public_api.is_public_apis_enabled(cfg):
        return {"items": None, "error": "public_apis_disabled"}
    params = {"query": topic, "page_size": DEPTH_LIMITS.get(depth, 25)}
    return public_api.fetch_json(
        ENDPOINT,
        params=params,
        user_agent_suffix="docker-hub-adapter",
    )


def parse_docker_hub_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    results = response["items"].get("results") or []
    out = []
    for r in results:
        name = r.get("repo_name") or r.get("name")
        if not name:
            continue
        out.append({
            "id": f"dockerhub:{name}",
            "title": f"{name} — {(r.get('short_description') or '')[:120]}",
            "snippet": (r.get("short_description") or "")[:500],
            "url": f"https://hub.docker.com/r/{name}",
            "source_domain": "hub.docker.com",
            "date": None,
            "relevance": 0.7,
            "why_relevant": f"Docker Hub image — {name}",
            "metadata": {
                "platform": "docker_hub",
                "repo_name": name,
                "pull_count": r.get("pull_count"),
                "star_count": r.get("star_count"),
                "is_official": r.get("is_official", False),
                "is_automated": r.get("is_automated", False),
            },
        })
    return out
