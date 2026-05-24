"""PyPI package lookup (signalsweep 3.21.0+).

PyPI's search endpoint is deprecated; we use the per-package JSON
endpoint `pypi.org/pypi/{pkg}/json` for known-package lookup (topic
treated as literal package name). For search-by-keyword, pair with
`libraries.io` (future work) or Google/Exa.

No auth. v3.6 public-APIs tier.
"""

from __future__ import annotations

from typing import Any

from . import public_api

ENDPOINT_TEMPLATE = "https://pypi.org/pypi/{pkg}/json"


def search_pypi(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not public_api.is_public_apis_enabled(cfg):
        return {"items": None, "error": "public_apis_disabled"}
    pkg = topic.strip()
    if not pkg:
        return {"items": {"info": {}}, "error": None}
    url = ENDPOINT_TEMPLATE.format(pkg=pkg)
    return public_api.fetch_json(
        url,
        user_agent_suffix="pypi-adapter",
        cache_key=f"pypi:{pkg}",
    )


def parse_pypi_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    info = response["items"].get("info") or {}
    name = info.get("name")
    if not name:
        return []
    releases = response["items"].get("releases") or {}
    upload_time = info.get("upload_time") or ""
    return [{
        "id": f"pypi:{name}",
        "title": f"{name} {info.get('version', '')} — {(info.get('summary') or '')[:120]}",
        "snippet": (info.get("summary") or info.get("description_content_type") or "PyPI package")[:500],
        "url": info.get("package_url") or f"https://pypi.org/project/{name}/",
        "source_domain": "pypi.org",
        "date": (upload_time or "")[:10] or None,
        "author": info.get("author") or info.get("maintainer"),
        "relevance": 0.7,
        "why_relevant": f"PyPI package — {name}",
        "metadata": {
            "platform": "pypi",
            "package_name": name,
            "version": info.get("version"),
            "license": info.get("license"),
            "requires_python": info.get("requires_python"),
            "release_count": len(releases),
            "home_page": info.get("home_page"),
        },
    }]
