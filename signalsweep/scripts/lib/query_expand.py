"""Dark-demand query expansion (signalsweep 3.28.1+).

Expands a product-noun topic into dark-demand search variations using
friction, absence, workaround, and ritual language patterns. Changes what
data comes IN rather than how it's processed after retrieval.

Usage: activated via `--dark-demand` CLI flag or `_dark_demand: true` in config.
Injects additional SubQuery entries into the query plan alongside the normal
planner-generated queries.

The expansion is depth-gated:
  quick   — 3 expansions (friction + absence + workaround)
  default — 6 expansions (+ edge-case + trust + ritual)
  deep    — 10 expansions (+ premium + discovery + analog + "almost" failures)
"""

from __future__ import annotations

from typing import Any

from . import schema

FRICTION_TEMPLATES = [
    '"{topic}" annoying OR frustrating OR "hard to" OR messy OR ugly',
    '"{topic}" "too much" OR "too little" OR "not enough" OR confusing',
]

ABSENCE_TEMPLATES = [
    '"why is there no" OR "does anyone make" OR "I wish" {topic}',
    '"no good option" OR "can\'t find" OR "wish there was" {topic}',
]

WORKAROUND_TEMPLATES = [
    '{topic} hack OR DIY OR workaround OR "I use this instead"',
    '{topic} "not ideal but" OR "I combine" OR "I made my own"',
]

EDGE_CASE_TEMPLATES = [
    '{topic} "small space" OR "for renters" OR "for travel" OR "ADHD friendly"',
    '{topic} "for kids" OR "for seniors" OR "one handed" OR "no drilling"',
]

TRUST_TEMPLATES = [
    '{topic} "is this safe" OR "does this work" OR "side effects" OR "scam"',
    '"{topic}" "I don\'t trust" OR "claims" OR "actually work" OR "third party tested"',
]

RITUAL_TEMPLATES = [
    '{topic} "morning routine" OR "night routine" OR "Sunday reset" OR "meal prep"',
    '{topic} "new habit" OR "changed my routine" OR "every day now"',
]

PREMIUM_TEMPLATES = [
    '{topic} "I\'d pay more" OR "worth the money" OR "finally found" OR "premium"',
    '{topic} "expensive but worth" OR "better version" OR "upgrade"',
]

DISCOVERY_TEMPLATES = [
    '{topic} "I didn\'t know I needed" OR "solved a problem" OR "changed everything"',
    '{topic} "game changer" OR "why didn\'t I buy this sooner"',
]

ANALOG_TEMPLATES = [
    '{topic} "like Uber for" OR "like Airbnb for" OR "Netflix of" OR "subscription"',
]

ALMOST_FAILURE_TEMPLATES = [
    '{topic} "almost perfect" OR "great idea but" OR "works except" OR "close but"',
    '{topic} "wanted to love" OR "would buy again if" OR "3 stars"',
]

EXPANSION_TIERS = {
    "quick": [
        ("friction", FRICTION_TEMPLATES),
        ("absence", ABSENCE_TEMPLATES),
        ("workaround", WORKAROUND_TEMPLATES),
    ],
    "default": [
        ("friction", FRICTION_TEMPLATES),
        ("absence", ABSENCE_TEMPLATES),
        ("workaround", WORKAROUND_TEMPLATES),
        ("edge_case", EDGE_CASE_TEMPLATES),
        ("trust", TRUST_TEMPLATES),
        ("ritual", RITUAL_TEMPLATES),
    ],
    "deep": [
        ("friction", FRICTION_TEMPLATES),
        ("absence", ABSENCE_TEMPLATES),
        ("workaround", WORKAROUND_TEMPLATES),
        ("edge_case", EDGE_CASE_TEMPLATES),
        ("trust", TRUST_TEMPLATES),
        ("ritual", RITUAL_TEMPLATES),
        ("premium", PREMIUM_TEMPLATES),
        ("discovery", DISCOVERY_TEMPLATES),
        ("analog", ANALOG_TEMPLATES),
        ("almost_failure", ALMOST_FAILURE_TEMPLATES),
    ],
}

DARK_DEMAND_SOURCES = [
    "reddit", "hackernews", "stackoverflow", "x", "x_sc",
    "youtube", "tiktok", "bluesky", "producthunt",
    "rss_blogs", "grounding",
]

LABEL_PREFIX = "dark-demand"


def is_dark_demand_enabled(config: dict[str, Any]) -> bool:
    return bool(config.get("_dark_demand"))


def expand_topic(
    topic: str,
    depth: str = "default",
    available_sources: list[str] | None = None,
) -> list[schema.SubQuery]:
    """Generate dark-demand SubQuery expansions for a topic.

    Returns SubQuery objects that can be appended to a QueryPlan's subqueries.
    Each expansion targets social/community sources where dark-demand language
    is most likely to appear.
    """
    tiers = EXPANSION_TIERS.get(depth, EXPANSION_TIERS["default"])
    available = set(available_sources or [])

    target_sources = [s for s in DARK_DEMAND_SOURCES if s in available] if available else DARK_DEMAND_SOURCES[:5]
    if not target_sources:
        target_sources = list(available)[:5] if available else ["reddit", "grounding"]

    subqueries = []
    for category, templates in tiers:
        template = templates[0]
        search_query = template.replace("{topic}", topic)
        ranking_query = _ranking_query(topic, category)

        subqueries.append(schema.SubQuery(
            label=f"{LABEL_PREFIX}:{category}",
            search_query=search_query,
            ranking_query=ranking_query,
            sources=target_sources,
            weight=0.8,
        ))

    return subqueries


def inject_into_plan(
    plan: schema.QueryPlan,
    topic: str,
    depth: str,
    available_sources: list[str],
) -> schema.QueryPlan:
    """Add dark-demand expansion subqueries to an existing query plan."""
    expansions = expand_topic(topic, depth, available_sources)
    if not expansions:
        return plan

    combined = list(plan.subqueries) + expansions
    notes = list(plan.notes or [])
    notes.append(f"dark-demand-expansion: +{len(expansions)} subqueries")

    return schema.QueryPlan(
        intent=plan.intent,
        freshness_mode=plan.freshness_mode,
        cluster_mode=plan.cluster_mode,
        raw_topic=plan.raw_topic,
        subqueries=combined,
        source_weights=plan.source_weights,
        notes=notes,
    )


def _ranking_query(topic: str, category: str) -> str:
    templates = {
        "friction": f"What frustrations, annoyances, or pain points do people experience with {topic}?",
        "absence": f"What product or solution for {topic} do people wish existed but can't find?",
        "workaround": f"What hacks, DIY solutions, or workarounds do people use for {topic}?",
        "edge_case": f"What specific constraints or edge cases make existing {topic} solutions inadequate?",
        "trust": f"What safety concerns, trust issues, or skepticism do people have about {topic}?",
        "ritual": f"What new routines, habits, or rituals are forming around {topic}?",
        "premium": f"What would people pay more for in a better version of {topic}?",
        "discovery": f"What unexpected benefits or discoveries have people made related to {topic}?",
        "analog": f"What analogies or business model innovations are emerging for {topic}?",
        "almost_failure": f"What near-misses, partial successes, or 'almost perfect' experiences do people report with {topic}?",
    }
    return templates.get(category, f"Dark demand signals for {topic}")
