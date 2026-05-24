"""Normalization of source-specific payloads into the v3 generic item model."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from . import dates, schema


def filter_by_date_range(
    items: list[schema.SourceItem],
    from_date: str,
    to_date: str,
    require_date: bool = False,
) -> list[schema.SourceItem]:
    """Keep only items within the requested window."""
    filtered: list[schema.SourceItem] = []
    for item in items:
        if not item.published_at:
            if not require_date:
                filtered.append(item)
            continue
        if item.published_at < from_date or item.published_at > to_date:
            continue
        filtered.append(item)
    return filtered


def normalize_source_items(
    source: str,
    items: list[dict[str, Any]],
    from_date: str,
    to_date: str,
    freshness_mode: str = "balanced_recent",
) -> list[schema.SourceItem]:
    """Normalize raw source items, filter by date range, with evergreen fallback for how_to queries."""
    source = source.lower()
    normalizers = {
        "reddit": _normalize_reddit,
        "x": _normalize_x,
        "youtube": _normalize_youtube,
        "tiktok": lambda s, i, idx, fd, td: _normalize_shortform_video(s, i, idx, fd, td, "TK", "TikTok post"),
        "instagram": lambda s, i, idx, fd, td: _normalize_shortform_video(s, i, idx, fd, td, "IG", "Instagram reel"),
        "hackernews": _normalize_hackernews,
        "bluesky": lambda s, i, idx, fd, td: _normalize_microblog(s, i, idx, fd, td, "BS", "Bluesky post"),
        "truthsocial": lambda s, i, idx, fd, td: _normalize_microblog(s, i, idx, fd, td, "TS", "Truth Social post"),
        "threads": lambda s, i, idx, fd, td: _normalize_microblog(s, i, idx, fd, td, "TH", "Threads post"),
        "xquik": _normalize_x,
        "pinterest": _normalize_pinterest,
        "polymarket": _normalize_polymarket,
        "digg": _normalize_digg,
        "grounding": _normalize_grounding,
        "xiaohongshu": _normalize_grounding,
        "github": _normalize_github,
        "perplexity": _normalize_grounding,
        # Signalsweep-unique sources
        "linkedin": _normalize_linkedin,
        "stackoverflow": _normalize_stackoverflow,
        "rss_blogs": _normalize_rss_blog,
        "podcasts": _normalize_podcast,
        "producthunt": _normalize_producthunt,
        "x_sc": _normalize_x,  # ScrapeCreators X backend
        "sec_edgar": _normalize_sec_edgar,  # SEC EDGAR filings
        "arxiv": _normalize_grounding,  # arXiv preprints (web-article shape)
        "biorxiv": _normalize_grounding,  # bioRxiv preprints
        "medrxiv": _normalize_grounding,  # medRxiv preprints
        "semantic_scholar": _normalize_grounding,  # Semantic Scholar scholarly papers
        "openalex": _normalize_grounding,  # OpenAlex scholarly works
        "pubmed": _normalize_grounding,  # PubMed biomedical literature
        "datagov": _normalize_grounding,  # US government open-data catalog
        "bls": _normalize_grounding,  # US Bureau of Labor Statistics
        "worldbank": _normalize_grounding,  # World Bank indicator catalog
        "eurostat": _normalize_grounding,  # Eurostat statistics catalog
        "wiki_pageviews": _normalize_wiki_pageviews,  # aggregate pageviews summary
        "wiki_recent_changes": _normalize_grounding,  # Wikipedia edits (article-shape) — same shape as xai_x
        # Signalsweep-unique sources (v3.6.1 — public-data backlog)
        "uk_ons": _normalize_grounding,  # UK Office for National Statistics datasets
        "imf": _normalize_grounding,  # IMF dataflow catalog
        "crossref": _normalize_grounding,  # CrossRef DOI works
        "orcid": _normalize_grounding,  # ORCID researcher records
        "bea": _normalize_grounding,  # US Bureau of Economic Analysis datasets
        "usda_nass": _normalize_grounding,  # USDA NASS QuickStats agriculture
        "wikidata": _normalize_grounding,  # Wikidata entities (wbsearchentities)
        "pubmed_efetch": _normalize_grounding,  # PubMed full-abstract fetch (extension of pubmed)
        # Signalsweep-unique sources (v3.7 — Amazon/ecommerce intelligence)
        "keepa": _normalize_grounding,  # Amazon products (web-article shape with BSR/price metadata)
        "helium10": _normalize_grounding,  # Amazon product intel (web-article shape)
        "junglescout": _normalize_grounding,  # Amazon product intel (web-article shape)
        "datadive": _normalize_grounding,  # Amazon keyword intel (web-article shape)
        "smartscout": _normalize_grounding,  # Amazon brand intel (web-article shape)
        "amazon_reviews": _normalize_grounding,  # Amazon reviews via SC (web-article shape)
        "tiktok_shop": _normalize_grounding,  # TikTok Shop listings via SC (web-article shape)
        "sp_api": _normalize_grounding,  # SP-API catalog items (web-article shape)
        "ads_api": _normalize_grounding,  # Ads API campaigns (web-article shape)
        "google_shopping": _normalize_grounding,  # Exa shopping-domain results (web-article shape)
        # Signalsweep-unique sources (v3.8 — Deep Research LLM providers)
        # All five share the synthesis+citations shape; reuse _normalize_grounding.
        "chatgpt_deep_research": _normalize_grounding,
        "claude_research": _normalize_grounding,
        "gemini_deep_research": _normalize_grounding,
        "grok_deepsearch": _normalize_grounding,
        "openrouter_research": _normalize_grounding,
        # Signalsweep-unique sources (v3.9 — Demand signals)
        # All 13 use trend-shape via build_trend_item; reuse _normalize_grounding.
        "google_trends": _normalize_grounding,
        "pinterest_trends": _normalize_grounding,
        "tiktok_creative_center": _normalize_grounding,
        "amazon_autocomplete": _normalize_grounding,
        "youtube_trending": _normalize_grounding,
        "soovle": _normalize_grounding,
        "answer_socrates": _normalize_grounding,
        "keyword_sheeter": _normalize_grounding,
        "sparktoro": _normalize_grounding,
        "exploding_topics": _normalize_grounding,
        "answerthepublic": _normalize_grounding,
        "alsoasked": _normalize_grounding,
        "glimpse": _normalize_grounding,
        # Signalsweep-unique sources (v3.14 — Non-Amazon marketplace expansion)
        "etsy": _normalize_grounding,
        "pinterest_commerce": _normalize_grounding,
        "amazon_vendor": _normalize_grounding,
        "walmart_marketplace": _normalize_grounding,
        "walmart_connect": _normalize_grounding,
        "tiktok_shop_seller": _normalize_grounding,
        # Signalsweep-unique sources (v3.15 — Patents/Legal/Regulatory)
        "federal_register": _normalize_grounding,
        "fda_openfda": _normalize_grounding,
        "courtlistener": _normalize_grounding,
        "uspto_patents": _normalize_grounding,
        "epo_ops": _normalize_grounding,
        # Signalsweep-unique sources (v3.16 — Meta Ad Library)
        "meta_ad_library": _normalize_grounding,
        # Signalsweep-unique sources (v3.16.1 — Google Ads Transparency)
        "google_ads_transparency": _normalize_grounding,
        # Signalsweep-unique sources (v3.16.2 — TikTok Ads Library)
        "tiktok_ads_library": _normalize_grounding,
        # Signalsweep-unique sources (v3.16.3 — LinkedIn Ad Library)
        "linkedin_ad_library": _normalize_grounding,
        # Signalsweep-unique sources (v3.16.4 — Wayback Machine CDX)
        "wayback_machine_cdx": _normalize_grounding,
        # Signalsweep-unique sources (v3.17.0 — Review aggregation)
        "app_store_reviews": _normalize_grounding,
        "yelp_fusion": _normalize_grounding,
        "trustpilot": _normalize_grounding,
        "g2": _normalize_grounding,
        "capterra": _normalize_grounding,
        "google_play_reviews": _normalize_grounding,
        # Signalsweep-unique sources (v3.18.0 — Financial markets)
        "fred": _normalize_grounding,
        "alpha_vantage": _normalize_grounding,
        "polygon_io": _normalize_grounding,
        "finnhub": _normalize_grounding,
        "sec_xbrl": _normalize_grounding,
        # Signalsweep-unique sources (v3.19.0 — Weather/environmental)
        "noaa": _normalize_grounding,
        "openweather": _normalize_grounding,
        "epa_airnow": _normalize_grounding,
        "nasa_power": _normalize_grounding,
        # Signalsweep-unique sources (v3.20.0 — News aggregation)
        "google_news": _normalize_grounding,
        "newsapi": _normalize_grounding,
        "gdelt": _normalize_grounding,
        "mediacloud": _normalize_grounding,
        # Signalsweep-unique sources (v3.21.0 — Developer signals)
        "npm_registry": _normalize_grounding,
        "pypi": _normalize_grounding,
        "homebrew": _normalize_grounding,
        "docker_hub": _normalize_grounding,
        # Signalsweep-unique sources (v3.22.0 — Crypto/on-chain)
        "coingecko": _normalize_grounding,
        "defillama": _normalize_grounding,
        "etherscan": _normalize_grounding,
        "dune": _normalize_grounding,
        # Signalsweep-unique sources (v3.23.0 — Federated social)
        "mastodon": _normalize_grounding,
        "lemmy": _normalize_grounding,
        "farcaster": _normalize_grounding,
        "discord": _normalize_grounding,
        # Signalsweep-unique sources (v3.24.0 — Geographic/Events/Gov stats)
        "cdc_data": _normalize_grounding,
        "usda_ers": _normalize_grounding,
        "google_places": _normalize_grounding,
        "foursquare": _normalize_grounding,
        "eventbrite": _normalize_grounding,
        "meetup": _normalize_grounding,
        # Signalsweep-unique sources (v3.25.0 — Market/creator/podcast envelopes)
        "crunchbase": _normalize_grounding,
        "similarweb": _normalize_grounding,
        "builtwith": _normalize_grounding,
        "buzzsumo": _normalize_grounding,
        "listen_notes": _normalize_grounding,
        "podchaser": _normalize_grounding,
        # Signalsweep-unique sources (v3.27.0 — Latent demand signal sources)
        "cpsc_saferproducts": _normalize_grounding,
        "instacart_trends": _normalize_grounding,
        "amazon_brand_analytics": _normalize_grounding,
        "shopify_analytics": _normalize_grounding,
        # Signalsweep-unique sources (v3.28.0 — Dark demand signal sources)
        "aftership_returns": _normalize_grounding,
        "cfpb_complaints": _normalize_grounding,
        "common_crawl": _normalize_grounding,
        "gorgias_tickets": _normalize_grounding,
        "google_patents": _normalize_grounding,
        "indiegogo": _normalize_grounding,
        "kickstarter": _normalize_grounding,
        "klaviyo_events": _normalize_grounding,
        "loop_returns": _normalize_grounding,
        "nhtsa_complaints": _normalize_grounding,
        "nutritionix": _normalize_grounding,
        "open_food_facts": _normalize_grounding,
        "powerreviews": _normalize_grounding,
        "spotify_podcasts": _normalize_grounding,
        "stamped_reviews": _normalize_grounding,
        "usda_fooddata": _normalize_grounding,
        "yotpo_reviews": _normalize_grounding,
    }
    normalizer = normalizers.get(source)
    if normalizer is None:
        raise ValueError(f"Unsupported source: {source}")
    normalized = [normalizer(source, item, index, from_date, to_date) for index, item in enumerate(items)]
    require_date = source == "grounding"
    filtered = filter_by_date_range(normalized, from_date, to_date, require_date=require_date)
    if filtered:
        return filtered
    if freshness_mode == "evergreen_ok" and source == "youtube":
        if require_date:
            return [item for item in normalized if item.published_at]
        return normalized
    return filtered


def _remap_comments(
    raw: list[Any],
    score_keys: tuple[str, ...],
    excerpt_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Normalize comments from any source into the shared top-comment shape."""
    out: list[dict[str, Any]] = []
    for raw_c in raw:
        if not isinstance(raw_c, dict):
            continue
        score = _first_present(raw_c, score_keys, default=0)
        excerpt = _first_present(raw_c, excerpt_keys, default="")
        try:
            score_int = int(score or 0)
        except (TypeError, ValueError):
            score_int = 0
        entry: dict[str, Any] = {
            "score": score_int,
            "excerpt": str(excerpt or "")[:400],
            "author": str(raw_c.get("author") or ""),
            "date": str(raw_c.get("date") or ""),
        }
        if raw_c.get("url"):
            entry["url"] = str(raw_c["url"])
        out.append(entry)
    return out


def _first_present(d: dict[str, Any], keys: tuple[str, ...], default: Any) -> Any:
    for key in keys:
        if key in d and d[key] not in (None, ""):
            return d[key]
    return default


def _join_comment_excerpts(
    top_comments: list[Any],
    key: str,
    limit: int = 3,
) -> str:
    return " ".join(
        str(comment.get(key) or "").strip()
        for comment in top_comments[:limit]
        if isinstance(comment, dict)
    )


def _domain_from_url(url: str) -> str | None:
    if not url:
        return None
    domain = urlparse(url).netloc.strip().lower()
    return domain or None


def _date_confidence(item: dict[str, Any], from_date: str, to_date: str, default: str = "low") -> str:
    if item.get("date_confidence"):
        return str(item["date_confidence"])
    date_value = item.get("date")
    if not date_value:
        return default
    return dates.get_date_confidence(str(date_value), from_date, to_date)


def _source_item(
    *,
    item_id: str,
    source: str,
    title: str,
    body: str,
    url: str,
    published_at: str | None,
    date_confidence: str,
    relevance_hint: float,
    why_relevant: str,
    author: str | None = None,
    container: str | None = None,
    engagement: dict[str, float | int] | None = None,
    snippet: str = "",
    metadata: dict[str, Any] | None = None,
) -> schema.SourceItem:
    return schema.SourceItem(
        item_id=item_id,
        source=source,
        title=title.strip() or body.strip()[:160] or item_id,
        body=body.strip(),
        url=url.strip(),
        author=(author or "").strip() or None,
        container=(container or "").strip() or None,
        published_at=published_at,
        date_confidence=date_confidence,
        engagement=engagement or {},
        relevance_hint=max(0.0, min(1.0, float(relevance_hint or 0.0))),
        why_relevant=why_relevant.strip(),
        snippet=snippet.strip(),
        metadata=metadata or {},
    )


def _normalize_reddit(
    source: str,
    item: dict[str, Any],
    index: int,
    from_date: str,
    to_date: str,
) -> schema.SourceItem:
    top_comments = item.get("top_comments") or []
    comment_text = _join_comment_excerpts(top_comments, "excerpt")
    body = "\n".join(
        part
        for part in [
            str(item.get("title") or "").strip(),
            str(item.get("selftext") or "").strip(),
            comment_text,
        ]
        if part
    )
    return _source_item(
        item_id=str(item.get("id") or f"R{index + 1}"),
        source=source,
        title=str(item.get("title") or ""),
        body=body,
        url=str(item.get("url") or ""),
        author=None,
        container=str(item.get("subreddit") or ""),
        published_at=item.get("date"),
        date_confidence=_date_confidence(item, from_date, to_date),
        engagement=item.get("engagement") or {},
        relevance_hint=item.get("relevance", 0.5),
        why_relevant=str(item.get("why_relevant") or ""),
        snippet=comment_text or str(item.get("selftext") or "")[:400],
        metadata={
            "top_comments": top_comments,
            "comment_insights": item.get("comment_insights") or [],
        },
    )


def _normalize_x(
    source: str,
    item: dict[str, Any],
    index: int,
    from_date: str,
    to_date: str,
) -> schema.SourceItem:
    text = str(item.get("text") or "").strip()
    return _source_item(
        item_id=str(item.get("id") or f"X{index + 1}"),
        source=source,
        title=text[:140] or f"X post {index + 1}",
        body=text,
        url=str(item.get("url") or ""),
        author=str(item.get("author_handle") or "").lstrip("@"),
        published_at=item.get("date"),
        date_confidence=_date_confidence(item, from_date, to_date),
        engagement=item.get("engagement") or {},
        relevance_hint=item.get("relevance", 0.5),
        why_relevant=str(item.get("why_relevant") or ""),
    )


def _normalize_youtube(
    source: str,
    item: dict[str, Any],
    index: int,
    from_date: str,
    to_date: str,
) -> schema.SourceItem:
    transcript = str(item.get("transcript_snippet") or "").strip()
    description = str(item.get("description") or "").strip()
    title = str(item.get("title") or "").strip()
    highlights = item.get("transcript_highlights") or []
    metadata: dict[str, Any] = {}
    if highlights:
        metadata["transcript_highlights"] = highlights
    if item.get("captions_disabled"):
        metadata["captions_disabled"] = True
    metadata["top_comments"] = _remap_comments(
        item.get("top_comments") or [],
        score_keys=("score", "likes"),
        excerpt_keys=("excerpt", "text"),
    )
    return _source_item(
        item_id=str(item.get("video_id") or item.get("id") or f"YT{index + 1}"),
        source=source,
        title=title,
        body="\n".join(part for part in [title, description, transcript] if part),
        url=str(item.get("url") or ""),
        author=str(item.get("channel_name") or ""),
        published_at=item.get("date"),
        date_confidence=_date_confidence(item, from_date, to_date, default="high"),
        engagement=item.get("engagement") or {},
        relevance_hint=item.get("relevance", 0.5),
        why_relevant=str(item.get("why_relevant") or ""),
        snippet=transcript,
        metadata=metadata,
    )


def _normalize_shortform_video(
    source: str,
    item: dict[str, Any],
    index: int,
    from_date: str,
    to_date: str,
    id_prefix: str,
    default_title: str,
) -> schema.SourceItem:
    """Shared normalizer for TikTok and Instagram (identical structure)."""
    caption = str(item.get("caption_snippet") or "").strip()
    text = str(item.get("text") or "").strip()
    return _source_item(
        item_id=str(item.get("id") or f"{id_prefix}{index + 1}"),
        source=source,
        title=text[:140] or caption[:140] or f"{default_title} {index + 1}",
        body="\n".join(part for part in [text, caption] if part),
        url=str(item.get("url") or ""),
        author=str(item.get("author_name") or ""),
        published_at=item.get("date"),
        date_confidence=_date_confidence(item, from_date, to_date, default="high"),
        engagement=item.get("engagement") or {},
        relevance_hint=item.get("relevance", 0.5),
        why_relevant=str(item.get("why_relevant") or ""),
        snippet=caption,
        metadata={
            "hashtags": item.get("hashtags") or [],
            "top_comments": _remap_comments(
                item.get("top_comments") or [],
                score_keys=("score", "digg_count", "likes"),
                excerpt_keys=("excerpt", "text"),
            ),
        },
    )


def _normalize_pinterest(
    source: str,
    item: dict[str, Any],
    index: int,
    from_date: str,
    to_date: str,
) -> schema.SourceItem:
    """Normalizer for Pinterest pins (visual content with descriptions).

    Saves are the primary engagement signal, analogous to likes/upvotes.
    """
    description = str(item.get("description") or "").strip()
    return _source_item(
        item_id=str(item.get("pin_id") or item.get("id") or f"PI{index + 1}"),
        source=source,
        title=description[:140] or f"Pinterest pin {index + 1}",
        body=description,
        url=str(item.get("url") or ""),
        author=str(item.get("author") or ""),
        container=str(item.get("board") or ""),
        published_at=item.get("date"),
        date_confidence=_date_confidence(item, from_date, to_date, default="low"),
        engagement=item.get("engagement") or {},
        relevance_hint=item.get("relevance", 0.5),
        why_relevant=str(item.get("why_relevant") or ""),
        snippet=description[:400],
    )


def _normalize_hackernews(
    source: str,
    item: dict[str, Any],
    index: int,
    from_date: str,
    to_date: str,
) -> schema.SourceItem:
    top_comments = item.get("top_comments") or []
    comment_text = _join_comment_excerpts(top_comments, "text")
    title = str(item.get("title") or "").strip()
    body = "\n".join(part for part in [title, str(item.get("text") or "").strip(), comment_text] if part)
    return _source_item(
        item_id=str(item.get("id") or f"HN{index + 1}"),
        source=source,
        title=title or f"HN story {index + 1}",
        body=body,
        url=str(item.get("url") or item.get("hn_url") or ""),
        author=str(item.get("author") or ""),
        container="Hacker News",
        published_at=item.get("date"),
        date_confidence=_date_confidence(item, from_date, to_date, default="high"),
        engagement=item.get("engagement") or {},
        relevance_hint=item.get("relevance", 0.5),
        why_relevant=str(item.get("why_relevant") or ""),
        snippet=comment_text,
        metadata={
            "hn_url": item.get("hn_url"),
            "top_comments": top_comments,
            "comment_insights": item.get("comment_insights") or [],
        },
    )


def _normalize_microblog(
    source: str,
    item: dict[str, Any],
    index: int,
    from_date: str,
    to_date: str,
    id_prefix: str,
    default_title: str,
) -> schema.SourceItem:
    """Shared normalizer for Bluesky and Truth Social (identical structure)."""
    text = str(item.get("text") or "").strip()
    return _source_item(
        item_id=str(item.get("id") or f"{id_prefix}{index + 1}"),
        source=source,
        title=text[:140] or f"{default_title} {index + 1}",
        body=text,
        url=str(item.get("url") or ""),
        author=str(item.get("handle") or item.get("author_handle") or "").lstrip("@"),
        published_at=item.get("date"),
        date_confidence=_date_confidence(item, from_date, to_date, default="high"),
        engagement=item.get("engagement") or {},
        relevance_hint=item.get("relevance", 0.5),
        why_relevant=str(item.get("why_relevant") or ""),
        metadata={"display_name": item.get("display_name")},
    )


def _normalize_digg(
    source: str,
    item: dict[str, Any],
    index: int,
    from_date: str,
    to_date: str,
) -> schema.SourceItem:
    title = str(item.get("title") or "").strip()
    tldr = str(item.get("tldr") or "").strip()
    body = "\n\n".join(part for part in [title, tldr] if part)
    posts = item.get("posts") or []
    if not isinstance(posts, list):
        posts = []
    cluster_url_id = str(item.get("id") or f"DG{index + 1}")
    return _source_item(
        item_id=cluster_url_id,
        source=source,
        title=title or f"Digg cluster {index + 1}",
        body=body,
        url=str(item.get("url") or f"https://di.gg/ai/{cluster_url_id}"),
        author="",
        container="Digg",
        published_at=item.get("date"),
        date_confidence=_date_confidence(item, from_date, to_date, default="high"),
        engagement=item.get("engagement") or {},
        relevance_hint=item.get("relevance", 0.5),
        why_relevant=str(item.get("why_relevant") or ""),
        snippet=tldr[:400],
        metadata={
            "clusterUrlId": cluster_url_id,
            "tldr": tldr,
            "rank": (item.get("engagement") or {}).get("rank"),
            "uniqueAuthors": (item.get("engagement") or {}).get("uniqueAuthors"),
            "postCount": (item.get("engagement") or {}).get("postCount"),
            "firstPostAge": item.get("first_post_age"),
            "posts": posts,
        },
    )


def _normalize_polymarket(
    source: str,
    item: dict[str, Any],
    index: int,
    from_date: str,
    to_date: str,
) -> schema.SourceItem:
    title = str(item.get("title") or "").strip()
    question = str(item.get("question") or "").strip()
    engagement = {
        "volume": item.get("volume1mo") or item.get("volume24hr") or 0,
        "liquidity": item.get("liquidity") or 0,
    }
    return _source_item(
        item_id=str(item.get("id") or f"PM{index + 1}"),
        source=source,
        title=title or question or f"Polymarket event {index + 1}",
        body="\n".join(part for part in [title, question, str(item.get("price_movement") or "")] if part),
        url=str(item.get("url") or ""),
        author=None,
        container="Polymarket",
        published_at=item.get("date"),
        date_confidence=_date_confidence(item, from_date, to_date, default="high"),
        engagement=engagement,
        relevance_hint=item.get("relevance", 0.5),
        why_relevant=str(item.get("why_relevant") or ""),
        snippet=str(item.get("price_movement") or ""),
        metadata={
            "question": question,
            "end_date": item.get("end_date"),
            "outcome_prices": item.get("outcome_prices") or [],
            "outcomes_remaining": item.get("outcomes_remaining"),
        },
    )



def _normalize_github(
    source: str,
    item: dict[str, Any],
    index: int,
    from_date: str,
    to_date: str,
) -> schema.SourceItem:
    title = str(item.get("title") or "").strip()
    snippet_text = str(item.get("snippet") or "").strip()
    top_comments = item.get("metadata", {}).get("top_comments") or []
    comment_text = _join_comment_excerpts(top_comments, "excerpt")
    body = "\n".join(part for part in [title, snippet_text, comment_text] if part)
    metadata = item.get("metadata") or {}
    return _source_item(
        item_id=str(item.get("id") or f"GH{index + 1}"),
        source=source,
        title=title or f"GitHub item {index + 1}",
        body=body,
        url=str(item.get("url") or ""),
        author=str(item.get("author") or ""),
        container=str(item.get("container") or ""),
        published_at=item.get("date"),
        date_confidence=_date_confidence(item, from_date, to_date, default="high"),
        engagement=item.get("engagement") or {},
        relevance_hint=item.get("relevance", 0.5),
        why_relevant=str(item.get("why_relevant") or ""),
        snippet=comment_text or snippet_text[:400],
        metadata={
            "top_comments": top_comments,
            "labels": metadata.get("labels") or [],
            "state": metadata.get("state", ""),
            "is_pr": metadata.get("is_pr", False),
        },
    )

def _normalize_grounding(
    source: str,
    item: dict[str, Any],
    index: int,
    from_date: str,
    to_date: str,
) -> schema.SourceItem:
    title = str(item.get("title") or "").strip()
    snippet = str(item.get("snippet") or "").strip()
    url = str(item.get("url") or "").strip()
    return _source_item(
        item_id=str(item.get("id") or f"W{index + 1}"),
        source=source,
        title=title or _domain_from_url(url) or f"Web result {index + 1}",
        body="\n".join(part for part in [title, snippet] if part),
        url=url,
        author=None,
        container=str(item.get("source_domain") or _domain_from_url(url) or ""),
        published_at=item.get("date"),
        date_confidence=_date_confidence(item, from_date, to_date),
        engagement=item.get("engagement") or {},
        relevance_hint=item.get("relevance", 0.5),
        why_relevant=str(item.get("why_relevant") or ""),
        snippet=snippet,
        metadata=item.get("metadata") or {},
    )


# ---------------------------------------------------------------------------
# Signalsweep-unique source normalizers (adapters for v3 source-module contract)
# ---------------------------------------------------------------------------


def _normalize_linkedin(
    source: str,
    item: dict[str, Any],
    index: int,
    from_date: str,
    to_date: str,
) -> schema.SourceItem:
    """LinkedIn post via ScrapeCreators — microblog-shaped with named author."""
    text = str(item.get("text") or "").strip()
    author_name = str(item.get("author_name") or "").strip()
    author_headline = str(item.get("author_headline") or "").strip()
    return _source_item(
        item_id=str(item.get("id") or f"LI{index + 1}"),
        source=source,
        title=text[:140] or f"LinkedIn post {index + 1}",
        body=text,
        url=str(item.get("url") or ""),
        author=author_name or None,
        container=author_headline or None,
        published_at=item.get("date"),
        date_confidence=_date_confidence(item, from_date, to_date),
        engagement=item.get("engagement") or {},
        relevance_hint=item.get("relevance", 0.5),
        why_relevant=str(item.get("why_relevant") or ""),
    )


def _normalize_stackoverflow(
    source: str,
    item: dict[str, Any],
    index: int,
    from_date: str,
    to_date: str,
) -> schema.SourceItem:
    """Stack Overflow question — title + body_snippet + score/answers engagement."""
    title = str(item.get("title") or "").strip()
    body_snippet = str(item.get("body_snippet") or "").strip()
    metadata = {
        "tags": item.get("tags") or [],
        "question_id": item.get("question_id"),
        "is_answered": item.get("is_answered", False),
        "accepted_answer_id": item.get("accepted_answer_id"),
    }
    return _source_item(
        item_id=str(item.get("question_id") or f"SO{index + 1}"),
        source=source,
        title=title or f"Stack Overflow question {index + 1}",
        body="\n".join(part for part in [title, body_snippet] if part),
        url=str(item.get("url") or ""),
        author=str(item.get("author") or "").strip() or None,
        container="stackoverflow.com",
        published_at=item.get("date"),
        date_confidence=_date_confidence(item, from_date, to_date),
        engagement=item.get("engagement") or {},
        relevance_hint=item.get("relevance", 0.5),
        why_relevant=str(item.get("why_relevant") or ""),
        snippet=body_snippet,
        metadata=metadata,
    )


def _normalize_rss_blog(
    source: str,
    item: dict[str, Any],
    index: int,
    from_date: str,
    to_date: str,
) -> schema.SourceItem:
    """RSS blog article (Medium/Substack) — web-article-shaped with author + platform."""
    title = str(item.get("title") or "").strip()
    description = str(item.get("description") or "").strip()
    platform = str(item.get("platform") or "").strip()
    url = str(item.get("url") or "").strip()
    metadata = {
        "platform": platform,
        "categories": item.get("categories") or [],
    }
    return _source_item(
        item_id=str(item.get("id") or f"BLOG{index + 1}"),
        source=source,
        title=title or _domain_from_url(url) or f"Blog post {index + 1}",
        body="\n".join(part for part in [title, description] if part),
        url=url,
        author=str(item.get("author") or "").strip() or None,
        container=platform or _domain_from_url(url),
        published_at=item.get("date"),
        date_confidence=_date_confidence(item, from_date, to_date),
        engagement=item.get("engagement") or {},
        relevance_hint=item.get("relevance", 0.5),
        why_relevant=str(item.get("why_relevant") or ""),
        snippet=description,
        metadata=metadata,
    )


def _normalize_podcast(
    source: str,
    item: dict[str, Any],
    index: int,
    from_date: str,
    to_date: str,
) -> schema.SourceItem:
    """Podcast episode via Taddy — title + description + podcast container + duration metadata."""
    title = str(item.get("title") or "").strip()
    description = str(item.get("description") or "").strip()
    podcast_name = str(item.get("podcast_name") or "").strip()
    metadata = {
        "duration": item.get("duration"),
        "audio_url": item.get("audio_url"),
        "episode_id": item.get("episode_id"),
        "transcript": item.get("transcript"),  # populated by search_and_enrich when available
    }
    return _source_item(
        item_id=str(item.get("episode_id") or f"POD{index + 1}"),
        source=source,
        title=title or f"Podcast episode {index + 1}",
        body="\n".join(part for part in [title, description] if part),
        url=str(item.get("audio_url") or ""),
        author=None,
        container=podcast_name or None,
        published_at=item.get("date"),
        date_confidence=_date_confidence(item, from_date, to_date),
        engagement=item.get("engagement") or {},
        relevance_hint=item.get("relevance", 0.5),
        why_relevant=str(item.get("why_relevant") or ""),
        snippet=description[:280],
        metadata=metadata,
    )


def _normalize_sec_edgar(
    source: str,
    item: dict[str, Any],
    index: int,
    from_date: str,
    to_date: str,
) -> schema.SourceItem:
    """SEC EDGAR filing — title + body + filing metadata preserved in metadata dict."""
    title = str(item.get("title") or "").strip()
    body = str(item.get("body") or "").strip()
    meta = item.get("metadata") or {}
    return _source_item(
        item_id=str(item.get("item_id") or f"SEC{index + 1}"),
        source=source,
        title=title or f"SEC filing {index + 1}",
        body=body,
        url=str(item.get("url") or ""),
        author=str(item.get("author") or "").strip() or None,
        container=str(item.get("container") or "").strip() or None,
        published_at=item.get("published_at"),
        date_confidence=_date_confidence(item, from_date, to_date, default="high"),
        engagement=item.get("engagement") or {},
        relevance_hint=item.get("relevance_hint", 0.5),
        why_relevant=str(item.get("why_relevant") or ""),
        metadata={
            "form": meta.get("form"),
            "cik": meta.get("cik"),
            "accession_number": meta.get("accession_number"),
            "company_name": meta.get("company_name"),
            "file_type": meta.get("file_type"),
        },
    )


def _normalize_wiki_pageviews(
    source: str,
    item: dict[str, Any],
    index: int,
    from_date: str,
    to_date: str,
) -> schema.SourceItem:
    """Wikipedia pageviews aggregate summary — preserves daily_series + peak_date in metadata."""
    meta = item.get("metadata") or {}
    return _source_item(
        item_id=str(item.get("item_id") or f"WIKI_PV{index + 1}"),
        source=source,
        title=str(item.get("title") or f"Wikipedia pageviews {index + 1}"),
        body=str(item.get("body") or ""),
        url=str(item.get("url") or ""),
        author=None,
        container=str(item.get("container") or "en.wikipedia.org"),
        published_at=item.get("published_at"),
        date_confidence=_date_confidence(item, from_date, to_date, default="high"),
        engagement=item.get("engagement") or {},
        relevance_hint=item.get("relevance_hint", 0.5),
        why_relevant=str(item.get("why_relevant") or ""),
        metadata={
            "article_title": meta.get("article_title"),
            "daily_series": meta.get("daily_series"),
            "avg_daily_views": meta.get("avg_daily_views"),
            "peak_date": meta.get("peak_date"),
            "peak_views": meta.get("peak_views"),
            "total_views": meta.get("total_views"),
            "data_points": meta.get("data_points"),
        },
    )


def _normalize_producthunt(
    source: str,
    item: dict[str, Any],
    index: int,
    from_date: str,
    to_date: str,
) -> schema.SourceItem:
    """Product Hunt launch — name + tagline + description with maker/website metadata."""
    name = str(item.get("name") or "").strip()
    tagline = str(item.get("tagline") or "").strip()
    description = str(item.get("description") or "").strip()
    title = name + (f" — {tagline}" if tagline else "")
    body = "\n".join(part for part in [title, description] if part)
    metadata = {
        "maker": item.get("maker"),
        "website": item.get("website"),
        "topics": item.get("topics") or [],
    }
    return _source_item(
        item_id=str(item.get("id") or f"PH{index + 1}"),
        source=source,
        title=title or f"Product Hunt launch {index + 1}",
        body=body,
        url=str(item.get("url") or ""),
        author=str(item.get("maker") or "").strip() or None,
        container="producthunt.com",
        published_at=item.get("date"),
        date_confidence=_date_confidence(item, from_date, to_date),
        engagement=item.get("engagement") or {},
        relevance_hint=item.get("relevance", 0.5),
        why_relevant=str(item.get("why_relevant") or ""),
        snippet=tagline or description[:280],
        metadata=metadata,
    )
