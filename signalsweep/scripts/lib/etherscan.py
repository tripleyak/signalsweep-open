"""Etherscan — Ethereum on-chain data (signalsweep 3.22.0+).

Endpoint: `api.etherscan.io/api`. Requires `ETHERSCAN_API_KEY`.
Free tier: 5 req/sec.

Topic shape: Ethereum address (0x-prefixed 40-hex) or contract name.
Non-address topics return graceful envelope. v3.7 paid-APIs + creds.
"""

from __future__ import annotations

import re
from typing import Any

from . import paid_api

ENDPOINT = "https://api.etherscan.io/api"
ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")


def _looks_like_address(topic: str) -> bool:
    return bool(ADDRESS_PATTERN.match(topic.strip()))


def search_etherscan(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = cfg.get("ETHERSCAN_API_KEY")
    if not api_key:
        return {"items": None, "error": "credentials_missing"}
    if not _looks_like_address(topic):
        return {"items": {"result": "0", "note": "non-address-topic"}, "error": None}
    params = {
        "module": "account",
        "action": "balance",
        "address": topic.strip(),
        "tag": "latest",
        "apikey": api_key,
    }
    return paid_api.fetch_json(ENDPOINT, params=params)


def parse_etherscan_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    payload = response["items"]
    if isinstance(payload, dict) and payload.get("note") == "non-address-topic":
        return []
    balance_wei = payload.get("result", "0") if isinstance(payload, dict) else "0"
    try:
        balance_eth = float(balance_wei) / 1e18
    except (TypeError, ValueError):
        balance_eth = 0.0
    return [{
        "id": f"etherscan:balance:{balance_wei}",
        "title": f"ETH balance — {balance_eth:.4f} ETH",
        "snippet": f"Balance at latest block: {balance_eth:.4f} ETH ({balance_wei} wei)",
        "url": "https://etherscan.io/",
        "source_domain": "etherscan.io",
        "date": None,
        "relevance": 0.7,
        "why_relevant": "Etherscan account balance lookup",
        "metadata": {
            "platform": "etherscan",
            "balance_wei": balance_wei,
            "balance_eth": balance_eth,
        },
    }]
