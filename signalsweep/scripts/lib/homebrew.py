"""Homebrew formulae catalog (signalsweep 3.21.0+).

Endpoint: `formulae.brew.sh/api/formula.json` (single file with all formulae,
cached 24h). Client-side filter by topic keyword against name/description.

No auth. v3.6 public-APIs tier.
"""

from __future__ import annotations

from typing import Any

from . import public_api

ENDPOINT = "https://formulae.brew.sh/api/formula.json"
DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_homebrew(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not public_api.is_public_apis_enabled(cfg):
        return {"items": None, "error": "public_apis_disabled"}
    return public_api.fetch_json(
        ENDPOINT,
        user_agent_suffix="homebrew-adapter",
        cache_key="homebrew:all-formulae",
    )


def parse_homebrew_response(
    response: dict[str, Any],
    topic: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    formulae = response["items"] if isinstance(response["items"], list) else []
    needle = topic.lower().strip()
    limit = DEPTH_LIMITS.get(depth, 25)
    matches = []
    for f in formulae:
        name = (f.get("name") or "").lower()
        desc = (f.get("desc") or "").lower()
        if needle and needle not in name and needle not in desc:
            continue
        matches.append(f)
        if len(matches) >= limit:
            break
    out = []
    for f in matches:
        name = f.get("name")
        if not name:
            continue
        out.append({
            "id": f"homebrew:{name}",
            "title": f"{name} — {(f.get('desc') or '')[:120]}",
            "snippet": (f.get("desc") or "")[:500],
            "url": f.get("homepage") or f"https://formulae.brew.sh/formula/{name}",
            "source_domain": "brew.sh",
            "date": None,
            "relevance": 0.7,
            "why_relevant": f"Homebrew formula — {name}",
            "metadata": {
                "platform": "homebrew",
                "formula_name": name,
                "homepage": f.get("homepage"),
                "license": f.get("license"),
                "tap": f.get("tap"),
                "dependencies": f.get("dependencies") or [],
            },
        })
    return out
