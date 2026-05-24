"""medRxiv preprint search via api.biorxiv.org (same backend, different server param).

Signalsweep 3.6+. Delegates the heavy lifting to biorxiv.py's shared helpers.
"""

from __future__ import annotations

from typing import Any

from . import biorxiv


def search_medrxiv(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return biorxiv.search_preprint_server("medrxiv", topic, from_date, to_date, depth, config)


def parse_medrxiv_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    max_items = biorxiv.DEPTH_LIMITS.get(depth, biorxiv.DEPTH_LIMITS["default"])
    return biorxiv._parse_preprint_collection(response, "medrxiv", query, max_items)
