"""DeFiLlama — DeFi TVL + protocols (signalsweep 3.22.0+).

Endpoint: `api.llama.fi/protocols`. No auth. v3.6 public-APIs tier.

Returns full protocol list and client-side filters by topic match.
"""

from __future__ import annotations

from typing import Any

from . import public_api

ENDPOINT = "https://api.llama.fi/protocols"
DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_defillama(
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
        user_agent_suffix="defillama-adapter",
        cache_key="defillama:all-protocols",
    )


def parse_defillama_response(
    response: dict[str, Any],
    topic: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    protocols = response["items"] if isinstance(response["items"], list) else []
    needle = (topic or "").lower().strip()
    limit = DEPTH_LIMITS.get(depth, 25)
    matches = []
    for p in protocols:
        name = (p.get("name") or "").lower()
        symbol = (p.get("symbol") or "").lower()
        category = (p.get("category") or "").lower()
        if needle and needle not in name and needle not in symbol and needle not in category:
            continue
        matches.append(p)
        if len(matches) >= limit:
            break
    out = []
    for p in matches:
        name = p.get("name")
        if not name:
            continue
        out.append({
            "id": f"defillama:{p.get('slug') or name}",
            "title": f"{name} — TVL ${round(p.get('tvl') or 0):,}",
            "snippet": f"{p.get('category', '')} · {p.get('chains') or []}".replace("[", "").replace("]", "").replace("'", "")[:500],
            "url": p.get("url") or f"https://defillama.com/protocol/{p.get('slug', name.lower())}",
            "source_domain": "defillama.com",
            "date": None,
            "relevance": 0.7,
            "why_relevant": f"DeFiLlama protocol — {name}",
            "metadata": {
                "platform": "defillama",
                "protocol_name": name,
                "category": p.get("category"),
                "tvl_usd": p.get("tvl"),
                "chains": p.get("chains") or [],
                "symbol": p.get("symbol"),
            },
        })
    return out
