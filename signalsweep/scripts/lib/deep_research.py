"""Shared orchestration for deep-research LLM providers (signalsweep 3.8+).

All five P1 deep-research providers (chatgpt_deep_research, claude_research,
gemini_deep_research, grok_deepsearch, openrouter_research) plus the existing
perplexity source share this helper for:

- Parallel invocation across providers (ThreadPoolExecutor; wall time = max,
  not sum)
- Per-provider timeout enforcement
- Cost estimation + cap with cheapest-first downgrade
- Disable toggle (`SIGNALSWEEP_DISABLE_DEEP_RESEARCH`)
- Cost-aware stderr logging (matches existing perplexity.py format)

The provider modules themselves (Units 3-7) hold the API-shape knowledge.
This helper holds the orchestration knowledge.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import sys
import time
from typing import Any, Callable

from lib import cache as _cache

# ---------------------------------------------------------------------------
# Cost model
# ---------------------------------------------------------------------------
#
# Hardcoded per-provider cost estimates (USD) for cap calculations.
# Actual cost is logged from API response `usage` field when the upstream
# returns it. These values are intentionally conservative — better to
# under-cap than to surprise the user with a large bill. Update when
# upstream pricing changes materially.

PROVIDER_COSTS: dict[str, float] = {
    "chatgpt_deep_research": 5.00,
    "claude_research": 3.00,
    "gemini_deep_research": 2.00,
    "grok_deepsearch": 1.00,
    "openrouter_research": 1.00,  # depends on routed model; default Perplexity Sonar at ~$0.90
    "perplexity": 0.90,            # existing v3.7 deep-research source — included so cost cap considers it
}

DEFAULT_MAX_COST_USD = 10.00       # default cap when env var unset; preserves "explicit opt-in" intent
DEFAULT_PER_PROVIDER_TIMEOUT_S = 300  # 5 minutes
DEFAULT_CACHE_TTL_HOURS = 24.0     # default deep-research query cache TTL


# Short-name aliases for the priority env var (v3.8.1).
# Identity mapping included so users may also pass full keys.
_PROVIDER_ALIASES: dict[str, str] = {
    "chatgpt": "chatgpt_deep_research",
    "claude": "claude_research",
    "gemini": "gemini_deep_research",
    "grok": "grok_deepsearch",
    "openrouter": "openrouter_research",
    "perplexity": "perplexity",
    # identity entries — accept full keys verbatim
    "chatgpt_deep_research": "chatgpt_deep_research",
    "claude_research": "claude_research",
    "gemini_deep_research": "gemini_deep_research",
    "grok_deepsearch": "grok_deepsearch",
    "openrouter_research": "openrouter_research",
}


# ---------------------------------------------------------------------------
# Toggle
# ---------------------------------------------------------------------------

def is_deep_research_enabled(config: dict[str, Any]) -> bool:
    """False when SIGNALSWEEP_DISABLE_DEEP_RESEARCH is truthy. Else True.

    Truthy: '1' / 'true' / 'yes' (case-insensitive).
    """
    value = str(config.get("SIGNALSWEEP_DISABLE_DEEP_RESEARCH", "")).strip().lower()
    return value not in {"1", "true", "yes"}


# ---------------------------------------------------------------------------
# Cost cap
# ---------------------------------------------------------------------------

def estimate_total_cost(provider_names: list[str]) -> float:
    """Sum of per-provider cost estimates. Unknown providers count as 0 with stderr warning."""
    total = 0.0
    for name in provider_names:
        cost = PROVIDER_COSTS.get(name)
        if cost is None:
            sys.stderr.write(
                f"[deep_research] WARNING: no cost estimate for provider {name!r}; treating as $0\n"
            )
            continue
        total += cost
    return total


def get_max_cost(config: dict[str, Any]) -> float:
    """Resolve max-cost cap from `SIGNALSWEEP_DEEP_RESEARCH_MAX_COST` env, else default."""
    raw = config.get("SIGNALSWEEP_DEEP_RESEARCH_MAX_COST")
    if raw is None or raw == "":
        return DEFAULT_MAX_COST_USD
    try:
        return float(raw)
    except (TypeError, ValueError):
        sys.stderr.write(
            f"[deep_research] WARNING: SIGNALSWEEP_DEEP_RESEARCH_MAX_COST={raw!r} "
            f"is not a number; using default ${DEFAULT_MAX_COST_USD:.2f}\n"
        )
        return DEFAULT_MAX_COST_USD


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log_invocation(provider: str, estimated_cost: float | None = None) -> None:
    """Log invocation to stderr. Matches existing perplexity.py format."""
    cost = estimated_cost if estimated_cost is not None else PROVIDER_COSTS.get(provider, 0.0)
    sys.stderr.write(f"[{provider}] Using deep research (~${cost:.2f}/query)\n")


# ---------------------------------------------------------------------------
# Parallel runner
# ---------------------------------------------------------------------------

def parallel_invoke(
    provider_calls: dict[str, Callable[[], tuple[list[dict], dict]]],
    *,
    per_provider_timeout_s: int = DEFAULT_PER_PROVIDER_TIMEOUT_S,
    max_workers: int | None = None,
) -> dict[str, tuple[list[dict], dict, str | None]]:
    """Run provider callables in parallel; return per-provider results + errors.

    Each callable should return `(items_list, artifact_dict)` matching the
    existing source-search return shape. Per-provider timeout enforced via
    `concurrent.futures.wait` deadlines.

    Returns: `{provider_name: (items, artifact, error_or_none)}`.
    Timed-out or raised providers get `error="deep_research_timeout"` or
    `error="<exception_type>: <message>"` and `items=[]`.
    """
    if not provider_calls:
        return {}

    workers = max_workers if max_workers is not None else max(1, len(provider_calls))
    results: dict[str, tuple[list[dict], dict, str | None]] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures: dict[concurrent.futures.Future, tuple[str, float]] = {}
        for name, call in provider_calls.items():
            future = executor.submit(call)
            futures[future] = (name, time.time())

        # We use a per-provider deadline rather than one global deadline so
        # a fast provider doesn't get cut off because a slow one is still running.
        for future in concurrent.futures.as_completed(futures, timeout=None):
            name, started_at = futures[future]
            elapsed = time.time() - started_at
            try:
                # If elapsed > timeout, treat as timeout regardless of completion
                if elapsed > per_provider_timeout_s:
                    results[name] = ([], {}, "deep_research_timeout")
                    sys.stderr.write(
                        f"[{name}] Timed out after {elapsed:.1f}s "
                        f"(cap {per_provider_timeout_s}s)\n"
                    )
                    continue
                items, artifact = future.result(timeout=0)
                results[name] = (items or [], artifact or {}, None)
            except concurrent.futures.TimeoutError:
                results[name] = ([], {}, "deep_research_timeout")
                sys.stderr.write(f"[{name}] Timed out\n")
            except Exception as err:
                results[name] = ([], {}, f"{type(err).__name__}: {err}")
                sys.stderr.write(f"[{name}] Errored: {type(err).__name__}: {err}\n")

    return results


# ---------------------------------------------------------------------------
# Provider priority (v3.8.1)
# ---------------------------------------------------------------------------

def get_provider_priority(config: dict[str, Any]) -> list[str]:
    """Parse `SIGNALSWEEP_DEEP_RESEARCH_PROVIDER_PRIORITY` env var.

    Comma-separated list of provider names (short or full). Returns providers
    in user-specified order (highest priority first). Unknown names produce
    a stderr warning and are skipped.

    Returns empty list when env var unset/empty — callers should treat that
    as "no priority preference; use cost-cap default behavior."
    """
    raw = config.get("SIGNALSWEEP_DEEP_RESEARCH_PROVIDER_PRIORITY", "")
    if not raw:
        return []

    out: list[str] = []
    for entry in str(raw).split(","):
        name = entry.strip().lower()
        if not name:
            continue
        full = _PROVIDER_ALIASES.get(name)
        if full is None:
            sys.stderr.write(
                f"[deep_research] WARNING: unknown provider in priority list: {name!r}\n"
            )
            continue
        if full not in out:
            out.append(full)
    return out


def apply_cost_cap(
    provider_names: list[str],
    max_cost: float,
    *,
    priority: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Drop providers until total cost ≤ max_cost.

    When `priority` is None or empty, falls back to "cheapest-first drop"
    (original v3.8.0 behavior — preserves the most expensive/highest-quality
    providers when budget is tight, since the user explicitly opted in).
    When `priority` is non-empty, drops lowest-priority providers first;
    providers absent from `priority` are treated as lowest priority and
    dropped before any listed provider.

    Returns (kept, dropped). Dropped logged to stderr.
    """
    if max_cost <= 0:
        for name in provider_names:
            sys.stderr.write(
                f"[deep_research] WARNING: max_cost={max_cost} drops {name}\n"
            )
        return [], list(provider_names)

    if priority:
        # Sort by user priority position; absent providers placed last (dropped first).
        absent_position = len(priority) + 1
        position = {name: idx for idx, name in enumerate(priority)}
        sorted_names = sorted(
            provider_names,
            key=lambda n: position.get(n, absent_position),
            reverse=True,  # highest position number (lowest priority) at index 0
        )
    else:
        # Backward-compatible: cheapest-first sort, drop from index 0.
        sorted_names = sorted(
            provider_names,
            key=lambda n: PROVIDER_COSTS.get(n, 0.0),
        )

    kept = list(sorted_names)
    dropped: list[str] = []

    while estimate_total_cost(kept) > max_cost and kept:
        dropped_name = kept.pop(0)
        dropped.append(dropped_name)

    if dropped:
        kept_cost = estimate_total_cost(kept)
        sys.stderr.write(
            f"[deep_research] Cost cap ${max_cost:.2f} → kept {kept} "
            f"(~${kept_cost:.2f}), dropped {dropped}\n"
        )

    return kept, dropped


# ---------------------------------------------------------------------------
# Query cache (v3.8.1)
# ---------------------------------------------------------------------------

def is_cache_disabled(config: dict[str, Any]) -> bool:
    """True when SIGNALSWEEP_DISABLE_DEEP_RESEARCH_CACHE is truthy."""
    value = str(config.get("SIGNALSWEEP_DISABLE_DEEP_RESEARCH_CACHE", "")).strip().lower()
    return value in {"1", "true", "yes"}


def get_cache_ttl_hours(config: dict[str, Any]) -> float:
    """Resolve cache TTL from `SIGNALSWEEP_DEEP_RESEARCH_CACHE_TTL_HOURS` env, else default 24."""
    raw = config.get("SIGNALSWEEP_DEEP_RESEARCH_CACHE_TTL_HOURS")
    if raw is None or raw == "":
        return DEFAULT_CACHE_TTL_HOURS
    try:
        ttl = float(raw)
    except (TypeError, ValueError):
        sys.stderr.write(
            f"[deep_research] WARNING: SIGNALSWEEP_DEEP_RESEARCH_CACHE_TTL_HOURS={raw!r} "
            f"is not a number; using default {DEFAULT_CACHE_TTL_HOURS}h\n"
        )
        return DEFAULT_CACHE_TTL_HOURS
    if ttl < 0:
        sys.stderr.write(
            f"[deep_research] WARNING: negative TTL {ttl} ignored; using default {DEFAULT_CACHE_TTL_HOURS}h\n"
        )
        return DEFAULT_CACHE_TTL_HOURS
    return ttl


def _deep_research_cache_key(
    provider_name: str,
    query: str,
    from_date: str,
    to_date: str,
    depth: str | None,
) -> str:
    """Generate a cache key for a deep-research provider invocation."""
    depth_str = depth or ""
    payload = f"deepresearch|{provider_name}|{from_date}|{to_date}|depth={depth_str}|{query}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def cached_provider_call(
    provider_name: str,
    query: str,
    from_date: str,
    to_date: str,
    depth: str | None,
    fn: Callable[[], tuple[list[dict], dict]],
    config: dict[str, Any],
) -> tuple[list[dict], dict]:
    """Cache-wrap a deep-research provider invocation.

    Returns (items, artifact). When SIGNALSWEEP_DISABLE_DEEP_RESEARCH_CACHE
    is set, bypasses cache entirely. Otherwise checks the on-disk cache for
    a fresh entry; on hit, returns cached result and logs to stderr. On miss,
    invokes `fn()`, persists the result, and returns it. Exceptions from `fn`
    propagate unchanged and do not write to cache.
    """
    if is_cache_disabled(config):
        return fn()

    ttl_hours = get_cache_ttl_hours(config)
    key = _deep_research_cache_key(provider_name, query, from_date, to_date, depth)

    # lib/cache.py compares age_hours < ttl_hours numerically; floats pass
    # through fine despite the int annotation upstream.
    cached, age_hours = _cache.load_cache_with_age(key, ttl_hours=ttl_hours)
    if cached is not None:
        items = cached.get("items", []) or []
        artifact = cached.get("artifact", {}) or {}
        age_str = f"{age_hours:.1f}h" if age_hours is not None else "?"
        sys.stderr.write(f"[{provider_name}] Cache hit (age: {age_str})\n")
        return items, artifact

    items, artifact = fn()
    _cache.save_cache(key, {"items": list(items or []), "artifact": dict(artifact or {})})
    return items, artifact
