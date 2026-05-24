"""AnswerSocrates question-phrased search demand (signalsweep 3.9.0+).

AnswerSocrates aggregates question-phrased search queries (Who/What/Where/
When/Why/How) from Google autocomplete — similar to AnswerThePublic but
free. Public-facing research tool; endpoint may drift.

No auth required.

Endpoint: https://answersocrates.com/
"""

from __future__ import annotations

from typing import Any

from . import demand_signals


SEARCH_URL = "https://answersocrates.com/api/search"

DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}

QUESTION_PREFIXES = ("who", "what", "where", "when", "why", "how")


def search_answer_socrates(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if not demand_signals.is_demand_signals_enabled(config):
        return demand_signals.disabled_envelope()

    params = {"q": topic, "language": "en"}
    return demand_signals.fetch_trends_json(
        SEARCH_URL,
        params=params,
        cache_key=f"answer_socrates:{topic}",
        user_agent_suffix="(answer_socrates-adapter)",
    )


def parse_answer_socrates_response(
    response: dict[str, Any],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
    depth: str = "default",
) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []

    payload = response["items"]
    if not isinstance(payload, dict):
        return []

    # Expected shape: {"questions": {"who": [...], "what": [...], ...}}
    # Fall back to flat list if structure differs.
    questions = payload.get("questions") or payload.get("results") or payload
    limit = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])

    parsed = []

    if isinstance(questions, dict):
        for prefix in QUESTION_PREFIXES:
            items = questions.get(prefix) or []
            if not isinstance(items, list):
                continue
            for q in items:
                q_text = q if isinstance(q, str) else (q.get("text") if isinstance(q, dict) else None)
                if not q_text or not isinstance(q_text, str):
                    continue
                parsed.append(_build_item(q_text.strip(), prefix, query, to_date))
                if len(parsed) >= limit:
                    return parsed
    elif isinstance(questions, list):
        for q in questions:
            q_text = q if isinstance(q, str) else (q.get("text") if isinstance(q, dict) else None)
            if not q_text or not isinstance(q_text, str):
                continue
            parsed.append(_build_item(q_text.strip(), "question", query, to_date))
            if len(parsed) >= limit:
                return parsed

    return parsed


def _build_item(text: str, prefix: str, query: str, to_date: str) -> dict[str, Any]:
    return demand_signals.build_trend_item(
        item_id=f"socrates:{prefix}:{text[:40]}",
        title=text,
        snippet=f"{prefix.title()} question from AnswerSocrates",
        url=f"https://answersocrates.com/?q={query}",
        source_domain="answersocrates.com",
        relevance=0.6,
        why_relevant=f"Question demand: {text[:60]}",
        date=to_date or None,
        metadata={"question_prefix": prefix, "query": query},
    )
