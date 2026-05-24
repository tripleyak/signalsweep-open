"""npm registry search (signalsweep 3.21.0+).

Endpoint: `registry.npmjs.org/-/v1/search`. No auth. v3.6 public-APIs tier.
"""

from __future__ import annotations

from typing import Any

from . import public_api

ENDPOINT = "https://registry.npmjs.org/-/v1/search"
DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_npm_registry(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not public_api.is_public_apis_enabled(cfg):
        return {"items": None, "error": "public_apis_disabled"}
    params = {"text": topic, "size": DEPTH_LIMITS.get(depth, 25)}
    return public_api.fetch_json(ENDPOINT, params=params, user_agent_suffix="npm-registry-adapter")


def parse_npm_registry_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    objects = response["items"].get("objects") or []
    out = []
    for o in objects:
        pkg = o.get("package") or {}
        name = pkg.get("name")
        if not name:
            continue
        out.append({
            "id": f"npm:{name}",
            "title": f"{name} — {(pkg.get('description') or '')[:120]}",
            "snippet": f"v{pkg.get('version', '?')} · {(pkg.get('keywords') or [''])[:5]}".replace("[", "").replace("]", "").replace("'", ""),
            "url": (pkg.get("links") or {}).get("npm") or f"https://www.npmjs.com/package/{name}",
            "source_domain": "npmjs.com",
            "date": (pkg.get("date") or "")[:10],
            "author": (pkg.get("publisher") or {}).get("username"),
            "relevance": min(0.9, float(o.get("score", {}).get("final") or 0.65)),
            "why_relevant": f"npm package — {name}",
            "metadata": {
                "platform": "npm",
                "package_name": name,
                "version": pkg.get("version"),
                "keywords": pkg.get("keywords") or [],
                "score_quality": (o.get("score") or {}).get("detail", {}).get("quality"),
                "score_popularity": (o.get("score") or {}).get("detail", {}).get("popularity"),
                "score_maintenance": (o.get("score") or {}).get("detail", {}).get("maintenance"),
            },
        })
    return out
