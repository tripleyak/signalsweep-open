"""v3.0.0 orchestration pipeline."""

from __future__ import annotations

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from shutil import which
from typing import Any

from . import (
    bird_x,
    bluesky,
    dates,
    dedupe,
    digg,
    entity_extract,
    env,
    github,
    grounding,
    hackernews,
    instagram,
    # Signalsweep-unique sources (v3.5)
    linkedin,
    normalize,
    perplexity,
    pinterest,
    planner,
    podcasts,
    polymarket,
    producthunt,
    providers,
    query,
    reddit,
    reddit_public,
    relevance,
    rerank,
    rss_blogs,
    schema,
    scrapecreators_x,
    signals,
    snippet,
    stackoverflow,
    threads,
    tiktok,
    truthsocial,
    xai_x,
    xiaohongshu_api,
    xquik,
    xurl_x,
    youtube_yt,
    # Signalsweep-unique sources (v3.6 — Free/Public Data bundle)
    arxiv,
    biorxiv,
    bls,
    datagov,
    eurostat,
    medrxiv,
    openalex,
    public_api,
    pubmed,
    sec_edgar,
    semantic_scholar,
    wiki_pageviews,
    wiki_recent_changes,
    worldbank,
    # Signalsweep-unique sources (v3.6.1 — public-data backlog)
    bea,
    crossref,
    imf,
    orcid,
    uk_ons,
    usda_nass,
    wikidata,
    # Signalsweep-unique sources (v3.7 — Amazon/ecommerce intelligence)
    ads_api,
    amazon_reviews,
    datadive,
    google_shopping,
    helium10,
    junglescout,
    keepa,
    paid_api,
    smartscout,
    sp_api,
    tiktok_shop,
    # Signalsweep-unique sources (v3.8 — Deep Research LLM providers)
    chatgpt_deep_research,
    claude_research,
    deep_research,
    gemini_deep_research,
    grok_deepsearch,
    openrouter_research,
    # Signalsweep-unique sources (v3.9 — Demand signals)
    alsoasked,
    amazon_autocomplete,
    answer_socrates,
    answerthepublic,
    demand_signals,
    exploding_topics,
    glimpse,
    google_trends,
    keyword_sheeter,
    pinterest_trends,
    soovle,
    sparktoro,
    tiktok_creative_center,
    youtube_trending,
    # Signalsweep-unique sources (v3.14 — Non-Amazon marketplace expansion)
    amazon_vendor,
    etsy,
    marketplace_oauth,
    pinterest_commerce,
    tiktok_shop_seller,
    walmart_connect,
    walmart_marketplace,
    # Signalsweep-unique sources (v3.15 — Patents/Legal/Regulatory)
    courtlistener,
    epo_ops,
    fda_openfda,
    federal_register,
    uspto_patents,
    # Signalsweep-unique sources (v3.16 — Meta Ad Library)
    meta_ad_library,
    # Signalsweep-unique sources (v3.16.1 — Google Ads Transparency Center)
    google_ads_transparency,
    # Signalsweep-unique sources (v3.16.2 — TikTok Ads Library)
    tiktok_ads_library,
    # Signalsweep-unique sources (v3.16.3 — LinkedIn Ad Library)
    linkedin_ad_library,
    # Signalsweep-unique sources (v3.16.4 — Wayback Machine CDX)
    wayback_machine_cdx,
    # Signalsweep-unique sources (v3.17.0 — Review aggregation)
    app_store_reviews,
    capterra,
    g2,
    google_play_reviews,
    trustpilot,
    yelp_fusion,
    # Signalsweep-unique sources (v3.18.0 — Financial markets)
    fred,
    alpha_vantage,
    polygon_io,
    finnhub,
    sec_xbrl,
    # Signalsweep-unique sources (v3.19.0 — Weather/environmental)
    noaa,
    openweather,
    epa_airnow,
    nasa_power,
    # Signalsweep-unique sources (v3.20.0 — News aggregation)
    google_news,
    newsapi,
    gdelt,
    mediacloud,
    # Signalsweep-unique sources (v3.21.0 — Developer signals)
    npm_registry,
    pypi,
    homebrew,
    docker_hub,
    # Signalsweep-unique sources (v3.22.0 — Crypto/on-chain)
    coingecko,
    defillama,
    etherscan,
    dune,
    # Signalsweep-unique sources (v3.23.0 — Federated social)
    mastodon,
    lemmy,
    farcaster,
    discord as discord_source,
    # Signalsweep-unique sources (v3.24.0 — Geographic/Events/Gov stats)
    cdc_data,
    usda_ers,
    google_places,
    foursquare,
    eventbrite,
    meetup,
    # Signalsweep-unique sources (v3.25.0 — Market/creator/podcast envelopes)
    crunchbase,
    similarweb,
    builtwith,
    buzzsumo,
    listen_notes,
    podchaser,
    # Signalsweep-unique sources (v3.27.0 — Latent demand signal sources)
    amazon_brand_analytics,
    cpsc_saferproducts,
    instacart_trends,
    shopify_analytics,
    sp_api_reports,
    # Signalsweep-unique modules (v3.28.0 — Dark demand)
    query_expand,
    # Signalsweep-unique sources (v3.28.0 — Dark demand signal sources)
    aftership_returns,
    cfpb_complaints,
    common_crawl,
    gorgias_tickets,
    google_patents,
    indiegogo,
    kickstarter,
    klaviyo_events,
    loop_returns,
    nhtsa_complaints,
    nutritionix,
    open_food_facts,
    powerreviews,
    spotify_podcasts,
    stamped_reviews,
    usda_fooddata,
    yotpo_reviews,
)
from .cluster import cluster_candidates
from .fusion import weighted_rrf

DEPTH_SETTINGS = {
    "quick": {"per_stream_limit": 6, "pool_limit": 15, "rerank_limit": 12},
    "default": {"per_stream_limit": 12, "pool_limit": 40, "rerank_limit": 40},
    "deep": {"per_stream_limit": 20, "pool_limit": 60, "rerank_limit": 60},
}

SEARCH_ALIAS = {
    "hn": "hackernews",
    "bsky": "bluesky",
    "truth": "truthsocial",
    "web": "grounding",
    "xhs": "xiaohongshu",
    "xquik": "xquik",
}

MAX_SOURCE_FETCHES: dict[str, int] = {"x": 2}

MOCK_AVAILABLE_SOURCES = [
    "reddit",
    "x",
    "youtube",
    "tiktok",
    "instagram",
    "hackernews",
    "bluesky",
    "truthsocial",
    "polymarket",
    "grounding",
    "xiaohongshu",
    "github",
    "perplexity",
    "threads",
    "pinterest",
    "xquik",
    "digg",
    # Signalsweep-unique sources (v3.5)
    "linkedin",
    "stackoverflow",
    "rss_blogs",
    "podcasts",
    "producthunt",
    "x_sc",
    # Signalsweep-unique sources (v3.6)
    "sec_edgar",
    "arxiv",
    "biorxiv",
    "medrxiv",
    "semantic_scholar",
    "openalex",
    "pubmed",
    "datagov",
    "bls",
    "worldbank",
    "eurostat",
    "wiki_pageviews",
    "wiki_recent_changes",
    # Signalsweep-unique sources (v3.6.1 — public-data backlog)
    "bea",
    "usda_nass",
    "uk_ons",
    "imf",
    "crossref",
    "orcid",
    "wikidata",
    "pubmed_efetch",
    # Signalsweep-unique sources (v3.7 — Amazon/ecommerce intelligence)
    "keepa",
    "helium10",
    "junglescout",
    "datadive",
    "smartscout",
    "amazon_reviews",
    "tiktok_shop",
    "sp_api",
    "ads_api",
    "google_shopping",
    # Signalsweep-unique sources (v3.8 — Deep Research LLM providers)
    "chatgpt_deep_research",
    "claude_research",
    "gemini_deep_research",
    "grok_deepsearch",
    "openrouter_research",
    # Signalsweep-unique sources (v3.9 — Demand signals)
    "google_trends",
    "pinterest_trends",
    "tiktok_creative_center",
    "amazon_autocomplete",
    "youtube_trending",
    "soovle",
    "answer_socrates",
    "keyword_sheeter",
    "sparktoro",
    "exploding_topics",
    "answerthepublic",
    "alsoasked",
    "glimpse",
    # Signalsweep-unique sources (v3.14 — Non-Amazon marketplace expansion)
    "etsy",
    "pinterest_commerce",
    "amazon_vendor",
    "walmart_marketplace",
    "walmart_connect",
    "tiktok_shop_seller",
    # Signalsweep-unique sources (v3.15 — Patents/Legal/Regulatory)
    "federal_register",
    "fda_openfda",
    "courtlistener",
    "uspto_patents",
    "epo_ops",
    # Signalsweep-unique sources (v3.16 — Meta Ad Library)
    "meta_ad_library",
    # Signalsweep-unique sources (v3.16.1 — Google Ads Transparency Center)
    "google_ads_transparency",
    # Signalsweep-unique sources (v3.16.2 — TikTok Ads Library)
    "tiktok_ads_library",
    # Signalsweep-unique sources (v3.16.3 — LinkedIn Ad Library)
    "linkedin_ad_library",
    # Signalsweep-unique sources (v3.16.4 — Wayback Machine CDX)
    "wayback_machine_cdx",
    # Signalsweep-unique sources (v3.17.0 — Review aggregation)
    "app_store_reviews",
    "capterra",
    "g2",
    "google_play_reviews",
    "trustpilot",
    "yelp_fusion",
    # Signalsweep-unique sources (v3.18.0 — Financial markets)
    "fred",
    "alpha_vantage",
    "polygon_io",
    "finnhub",
    "sec_xbrl",
    # Signalsweep-unique sources (v3.19.0 — Weather/environmental)
    "noaa",
    "openweather",
    "epa_airnow",
    "nasa_power",
    # Signalsweep-unique sources (v3.20.0 — News aggregation)
    "google_news",
    "newsapi",
    "gdelt",
    "mediacloud",
    # Signalsweep-unique sources (v3.21.0 — Developer signals)
    "npm_registry",
    "pypi",
    "homebrew",
    "docker_hub",
    # Signalsweep-unique sources (v3.22.0 — Crypto/on-chain)
    "coingecko",
    "defillama",
    "etherscan",
    "dune",
    # Signalsweep-unique sources (v3.23.0 — Federated social)
    "mastodon",
    "lemmy",
    "farcaster",
    "discord",
    # Signalsweep-unique sources (v3.24.0 — Geographic/Events/Gov stats)
    "cdc_data",
    "usda_ers",
    "google_places",
    "foursquare",
    "eventbrite",
    "meetup",
    # Signalsweep-unique sources (v3.25.0 — Market/creator/podcast envelopes)
    "crunchbase",
    "similarweb",
    "builtwith",
    "buzzsumo",
    "listen_notes",
    "podchaser",
    # Signalsweep-unique sources (v3.27.0 — Latent demand signal sources)
    "cpsc_saferproducts",
    "instacart_trends",
    "amazon_brand_analytics",
    "shopify_analytics",
    # Signalsweep-unique sources (v3.28.0 — Dark demand signal sources)
    "aftership_returns",
    "cfpb_complaints",
    "common_crawl",
    "gorgias_tickets",
    "google_patents",
    "indiegogo",
    "kickstarter",
    "klaviyo_events",
    "loop_returns",
    "nhtsa_complaints",
    "nutritionix",
    "open_food_facts",
    "powerreviews",
    "spotify_podcasts",
    "stamped_reviews",
    "usda_fooddata",
    "yotpo_reviews",
]


def normalize_requested_sources(sources: list[str] | None) -> list[str] | None:
    if not sources:
        return None
    normalized = []
    for source in sources:
        key = SEARCH_ALIAS.get(source.lower(), source.lower())
        if key not in normalized:
            normalized.append(key)
    return normalized


def available_sources(config: dict[str, Any], requested_sources: list[str] | None = None) -> list[str]:
    available: list[str] = []
    paid_enabled = paid_api.is_paid_apis_enabled(config)
    # reddit_public needs no API key - always available
    available.append("reddit")
    if paid_enabled and config.get("SCRAPECREATORS_API_KEY"):
        available.extend(["tiktok", "instagram"])
    x_source, x_method = env.get_x_source_with_method(config)
    if x_source and (x_method != "xai" or paid_enabled):
        available.append("x")
    if which("yt-dlp") or (paid_enabled and env.is_youtube_sc_available(config)):
        available.append("youtube")
    available.extend(["hackernews", "polymarket"])
    if config.get("GITHUB_TOKEN") or which("gh"):
        available.append("github")
    if public_api.is_public_apis_enabled(config):
        available.append("digg")
    if env.is_bluesky_available(config):
        available.append("bluesky")
    if env.is_truthsocial_available(config):
        available.append("truthsocial")
    if paid_enabled and (
        config.get("BRAVE_API_KEY")
        or config.get("EXA_API_KEY")
        or config.get("SERPER_API_KEY")
        or config.get("PARALLEL_API_KEY")
    ):
        available.append("grounding")
    # Perplexity Sonar: opt-in additive source via INCLUDE_SOURCES=perplexity
    include_sources = (config.get("INCLUDE_SOURCES") or "").lower().split(",")
    if paid_enabled and deep_research.is_deep_research_enabled(config) and config.get("OPENROUTER_API_KEY") and (
        "perplexity" in include_sources or (requested_sources and "perplexity" in requested_sources)
    ):
        available.append("perplexity")
    if requested_sources and "xiaohongshu" in requested_sources and env.is_xiaohongshu_available(config):
        available.append("xiaohongshu")
    if paid_enabled and env.is_threads_available(config):
        available.append("threads")
    if paid_enabled and requested_sources and "pinterest" in requested_sources and env.is_pinterest_available(config):
        available.append("pinterest")
    if env.is_xquik_available(config):
        available.append("xquik")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.5)
    # -----------------------------------------------------------------
    # StackOverflow and RSS blogs need no auth — always available
    available.extend(["stackoverflow", "rss_blogs"])
    # LinkedIn + ScrapeCreators X need SCRAPECREATORS_API_KEY
    if paid_enabled and config.get("SCRAPECREATORS_API_KEY"):
        available.extend(["linkedin", "x_sc"])
    # Podcasts via Taddy need both user id and api key
    if paid_enabled and config.get("TADDY_USER_ID") and config.get("TADDY_API_KEY"):
        available.append("podcasts")
    # Product Hunt needs bearer token
    if paid_enabled and config.get("PRODUCTHUNT_TOKEN"):
        available.append("producthunt")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.6 — Free/Public Data)
    # -----------------------------------------------------------------
    if public_api.is_public_apis_enabled(config):
        available.extend([
            "sec_edgar",
            "arxiv", "biorxiv", "medrxiv", "semantic_scholar", "openalex", "pubmed",
            "datagov", "bls", "worldbank", "eurostat",
            "wiki_pageviews", "wiki_recent_changes",
        ])
        # v3.6.1 — public-data backlog. All no-auth except bea/usda_nass which
        # ship with credentials_missing envelope (key required for real data).
        available.extend([
            "uk_ons", "imf", "crossref", "orcid", "wikidata", "pubmed_efetch",
            "bea", "usda_nass",
        ])
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.7 — Amazon/ecommerce intelligence)
    # Gated by SIGNALSWEEP_DISABLE_PAID_APIS + per-source credential checks.
    # -----------------------------------------------------------------
    if paid_enabled:
        if config.get("KEEPA_API_KEY"):
            available.append("keepa")
        if config.get("HELIUM10_API_KEY"):
            available.append("helium10")
        if config.get("JUNGLESCOUT_API_KEY"):
            available.append("junglescout")
        if config.get("DATADIVE_API_KEY"):
            available.append("datadive")
        if config.get("SMARTSCOUT_API_KEY"):
            available.append("smartscout")
        # ScrapeCreators-backed paid sources (reuse SC key from v3.5 env)
        if config.get("SCRAPECREATORS_API_KEY"):
            available.extend(["amazon_reviews", "tiktok_shop"])
        # Amazon SP-API: requires LWA trio
        lwa_ready = (
            config.get("AMAZON_LWA_REFRESH_TOKEN")
            and config.get("AMAZON_LWA_CLIENT_ID")
            and config.get("AMAZON_LWA_CLIENT_SECRET")
        )
        if lwa_ready:
            available.append("sp_api")
        # Amazon Ads API: LWA trio + a profile ID (either scalar or via active profile)
        if lwa_ready and (
            config.get("AMAZON_ADS_PROFILE_ID")
            or (config.get("AMAZON_ADS_PROFILES") and config.get("AMAZON_ADS_ACTIVE_PROFILE"))
        ):
            available.append("ads_api")
        # Google Shopping via Exa: reuses EXA_API_KEY (already set for grounding)
        if config.get("EXA_API_KEY"):
            available.append("google_shopping")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.8 — Deep Research LLM providers)
    # Two-locked opt-in: requires `_deep_research` config flag (set by --deep-research CLI)
    # AND explicit listing in `requested_sources` (--search=). Even with credentials,
    # these never auto-activate. Cost cap applied at dispatch time, not here.
    # -----------------------------------------------------------------
    if (
        config.get("_deep_research")
        and deep_research.is_deep_research_enabled(config)
        and requested_sources
    ):
        deep_research_providers = {
            "chatgpt_deep_research", "claude_research", "gemini_deep_research",
            "grok_deepsearch", "openrouter_research",
        }
        explicitly_requested = set(requested_sources) & deep_research_providers
        for provider in explicitly_requested:
            if _deep_research_provider_credentials(provider, config):
                available.append(provider)
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.9 — Demand signals)
    # Gated by SIGNALSWEEP_DISABLE_DEMAND_SIGNALS. Free/no-auth sources
    # always available. Credentialed sources ship with credentials_missing
    # envelope and are always available — their adapters self-report.
    # -----------------------------------------------------------------
    if demand_signals.is_demand_signals_enabled(config):
        # Free, no-auth sources
        available.extend([
            "google_trends", "pinterest_trends", "tiktok_creative_center",
            "amazon_autocomplete", "soovle", "answer_socrates", "keyword_sheeter",
        ])
        # Free-with-key (YouTube Data API v3): available if key present
        if config.get("YOUTUBE_API_KEY"):
            available.append("youtube_trending")
        # Paid SaaS: available only when key present; otherwise permanent envelope
        if config.get("SPARKTORO_API_KEY"):
            available.append("sparktoro")
        if config.get("EXPLODING_TOPICS_API_KEY"):
            available.append("exploding_topics")
        if config.get("ANSWERTHEPUBLIC_API_KEY"):
            available.append("answerthepublic")
        if config.get("ALSOASKED_API_KEY"):
            available.append("alsoasked")
        if config.get("GLIMPSE_API_KEY"):
            available.append("glimpse")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.14 — Non-Amazon marketplaces)
    # Gated by SIGNALSWEEP_DISABLE_PAID_APIS. All 6 credential-gated
    # (envelope-first). User activates as access lands.
    # -----------------------------------------------------------------
    if paid_enabled:
        if config.get("ETSY_API_KEY"):
            available.append("etsy")
        if (
            config.get("PINTEREST_CLIENT_ID")
            and config.get("PINTEREST_CLIENT_SECRET")
            and config.get("PINTEREST_OAUTH_REFRESH_TOKEN")
        ):
            available.append("pinterest_commerce")
        if (
            config.get("AMAZON_VENDOR_LWA_REFRESH_TOKEN")
            and config.get("AMAZON_VENDOR_LWA_CLIENT_ID")
            and config.get("AMAZON_VENDOR_LWA_CLIENT_SECRET")
        ):
            available.append("amazon_vendor")
        if (
            config.get("WALMART_MARKETPLACE_CLIENT_ID")
            and config.get("WALMART_MARKETPLACE_CLIENT_SECRET")
        ):
            available.append("walmart_marketplace")
        if (
            config.get("WALMART_CONNECT_CLIENT_ID")
            and config.get("WALMART_CONNECT_CLIENT_SECRET")
        ):
            available.append("walmart_connect")
        if (
            config.get("TIKTOK_SHOP_PARTNER_APP_KEY")
            and config.get("TIKTOK_SHOP_PARTNER_APP_SECRET")
            and config.get("TIKTOK_SHOP_PARTNER_ACCESS_TOKEN")
        ):
            available.append("tiktok_shop_seller")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.15 — Patents/Legal/Regulatory)
    # federal_register: no auth — gated only by v3.6 public-API toggle.
    # fda_openfda: no auth for 1k/day tier — gated by v3.6 toggle; API key optional.
    # courtlistener/uspto_patents/epo_ops: credential-gated, v3.7 paid toggle.
    # -----------------------------------------------------------------
    if public_api.is_public_apis_enabled(config):
        available.extend(["federal_register", "fda_openfda"])
    if paid_enabled:
        if config.get("COURTLISTENER_API_TOKEN"):
            available.append("courtlistener")
        if config.get("PATENTSVIEW_API_KEY"):
            available.append("uspto_patents")
        if config.get("EPO_OPS_CONSUMER_KEY") and config.get("EPO_OPS_CONSUMER_SECRET"):
            available.append("epo_ops")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.16 — Meta Ad Library)
    # Gated by SIGNALSWEEP_DISABLE_PAID_APIS + credential check.
    # -----------------------------------------------------------------
    if paid_enabled:
        if config.get("META_AD_LIBRARY_ACCESS_TOKEN"):
            available.append("meta_ad_library")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.16.1 — Google Ads Transparency)
    # No credentials required (reverse-engineered public endpoint); always
    # available when paid-APIs toggle enabled.
    # -----------------------------------------------------------------
    if paid_enabled:
        available.append("google_ads_transparency")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.16.2 — TikTok Ads Library)
    # No credentials required; gated by paid-APIs toggle.
    # -----------------------------------------------------------------
    if paid_enabled:
        available.append("tiktok_ads_library")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.16.3 — LinkedIn Ad Library)
    # Envelope-first: requires LinkedIn Marketing API 3-cred trio.
    # -----------------------------------------------------------------
    if paid_enabled:
        if (
            config.get("LINKEDIN_MARKETING_CLIENT_ID")
            and config.get("LINKEDIN_MARKETING_CLIENT_SECRET")
            and config.get("LINKEDIN_MARKETING_REFRESH_TOKEN")
        ):
            available.append("linkedin_ad_library")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.16.4 — Wayback Machine)
    # Public-data research tool; gated by v3.6 public-APIs toggle.
    # -----------------------------------------------------------------
    if public_api.is_public_apis_enabled(config):
        available.append("wayback_machine_cdx")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.17.0 — Review aggregation)
    # app_store_reviews: Apple iTunes public API, no auth — v3.6 public-APIs tier.
    # trustpilot/g2/capterra/google_play_reviews: scrape-friendly public pages,
    #   500ms polite-sleep — v3.7 paid-APIs tier alongside v3.9 scrape sources.
    # yelp_fusion: credentialed Yelp Fusion v3 API — v3.7 + YELP_API_KEY.
    # -----------------------------------------------------------------
    if public_api.is_public_apis_enabled(config):
        available.append("app_store_reviews")
    if paid_enabled:
        available.extend(["trustpilot", "g2", "capterra", "google_play_reviews"])
        if config.get("YELP_API_KEY"):
            available.append("yelp_fusion")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.18.0 — Financial markets)
    # fred/alpha_vantage/polygon_io/finnhub: credentialed paid-APIs tier.
    # sec_xbrl: public-data (no auth, User-Agent identifier requested by SEC).
    # -----------------------------------------------------------------
    if paid_enabled:
        if config.get("FRED_API_KEY"):
            available.append("fred")
        if config.get("ALPHAVANTAGE_API_KEY") or config.get("ALPHA_VANTAGE_API_KEY"):
            available.append("alpha_vantage")
        if config.get("POLYGON_API_KEY"):
            available.append("polygon_io")
        if config.get("FINNHUB_API_KEY"):
            available.append("finnhub")
    if public_api.is_public_apis_enabled(config):
        available.append("sec_xbrl")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.19.0 — Weather/environmental)
    # noaa/openweather/epa_airnow: credentialed paid-APIs.
    # nasa_power: no auth, v3.6 public-APIs toggle.
    # -----------------------------------------------------------------
    if paid_enabled:
        if config.get("NOAA_CDO_TOKEN"):
            available.append("noaa")
        if config.get("OPENWEATHER_API_KEY"):
            available.append("openweather")
        if config.get("EPA_AIRNOW_API_KEY"):
            available.append("epa_airnow")
    if public_api.is_public_apis_enabled(config):
        available.append("nasa_power")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.20.0 — News aggregation)
    # google_news / gdelt: no auth, v3.6 public-APIs tier.
    # newsapi / mediacloud: credentialed paid-APIs tier.
    # -----------------------------------------------------------------
    if public_api.is_public_apis_enabled(config):
        available.extend(["google_news", "gdelt"])
    if paid_enabled:
        if config.get("NEWSAPI_KEY") or config.get("NEWS_API_KEY"):
            available.append("newsapi")
        if config.get("MEDIACLOUD_API_KEY"):
            available.append("mediacloud")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.21.0 — Developer signals)
    # All 4 no-auth; v3.6 public-APIs tier.
    # -----------------------------------------------------------------
    if public_api.is_public_apis_enabled(config):
        available.extend(["npm_registry", "pypi", "homebrew", "docker_hub"])
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.22.0 — Crypto/on-chain)
    # coingecko / defillama: no auth required, v3.6 public-APIs.
    # etherscan / dune: credentialed, v3.7 paid-APIs.
    # -----------------------------------------------------------------
    if public_api.is_public_apis_enabled(config):
        available.extend(["coingecko", "defillama"])
    if paid_enabled:
        if config.get("ETHERSCAN_API_KEY"):
            available.append("etherscan")
        if config.get("DUNE_API_KEY"):
            available.append("dune")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.23.0 — Federated social)
    # mastodon/lemmy: no auth (public instances), v3.6 public-APIs.
    # farcaster/discord: credentialed, v3.7 paid-APIs.
    # -----------------------------------------------------------------
    if public_api.is_public_apis_enabled(config):
        available.extend(["mastodon", "lemmy"])
    if paid_enabled:
        if config.get("NEYNAR_API_KEY"):
            available.append("farcaster")
        if config.get("DISCORD_BOT_TOKEN") and config.get("DISCORD_GUILD_ID"):
            available.append("discord")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.24.0 — Geographic/Events/Gov stats)
    # cdc_data: no auth (optional CDC_APP_TOKEN), v3.6 public-APIs.
    # usda_ers/google_places/foursquare/eventbrite/meetup: credentialed, v3.7.
    # -----------------------------------------------------------------
    if public_api.is_public_apis_enabled(config):
        available.append("cdc_data")
    if paid_enabled:
        if config.get("USDA_ERS_API_KEY"):
            available.append("usda_ers")
        if config.get("GOOGLE_PLACES_API_KEY"):
            available.append("google_places")
        if config.get("FOURSQUARE_API_KEY"):
            available.append("foursquare")
        if config.get("EVENTBRITE_TOKEN"):
            available.append("eventbrite")
        if config.get("MEETUP_ACCESS_TOKEN"):
            available.append("meetup")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.25.0 — Market/creator/podcast envelopes)
    # All 6 credentialed, v3.7 paid-APIs tier.
    # -----------------------------------------------------------------
    if paid_enabled:
        if config.get("CRUNCHBASE_API_KEY"):
            available.append("crunchbase")
        if config.get("SIMILARWEB_API_KEY"):
            available.append("similarweb")
        if config.get("BUILTWITH_API_KEY"):
            available.append("builtwith")
        if config.get("BUZZSUMO_API_KEY"):
            available.append("buzzsumo")
        if config.get("LISTENNOTES_API_KEY") or config.get("LISTEN_NOTES_API_KEY"):
            available.append("listen_notes")
        if config.get("PODCHASER_ACCESS_TOKEN"):
            available.append("podchaser")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.27.0 — Latent demand signals)
    # cpsc_saferproducts / instacart_trends: no auth, v3.6 public-APIs tier.
    # amazon_brand_analytics: SP-API credentialed, v3.7 paid-APIs tier.
    # shopify_analytics: store-owner credentialed, v3.7 paid-APIs tier.
    # -----------------------------------------------------------------
    if public_api.is_public_apis_enabled(config):
        available.extend(["cpsc_saferproducts", "instacart_trends"])
    if paid_enabled:
        lwa_ready = (
            config.get("AMAZON_LWA_REFRESH_TOKEN")
            and config.get("AMAZON_LWA_CLIENT_ID")
            and config.get("AMAZON_LWA_CLIENT_SECRET")
        )
        if lwa_ready:
            available.append("amazon_brand_analytics")
        if config.get("SHOPIFY_STORE") and config.get("SHOPIFY_ACCESS_TOKEN"):
            available.append("shopify_analytics")
    # -----------------------------------------------------------------
    # Signalsweep-unique source availability (v3.28.0 — Dark demand signals)
    # -----------------------------------------------------------------
    if public_api.is_public_apis_enabled(config):
        available.extend(["cfpb_complaints", "common_crawl", "indiegogo", "kickstarter", "nhtsa_complaints", "open_food_facts", "usda_fooddata"])
    if paid_enabled:
        if config.get("KLAVIYO_API_KEY"):
            available.append("klaviyo_events")
        if config.get("YOTPO_APP_KEY"):
            available.append("yotpo_reviews")
        if config.get("GORGIAS_DOMAIN") and config.get("GORGIAS_EMAIL") and config.get("GORGIAS_API_KEY"):
            available.append("gorgias_tickets")
        if config.get("LOOP_RETURNS_API_KEY"):
            available.append("loop_returns")
        if config.get("AFTERSHIP_API_KEY"):
            available.append("aftership_returns")
        if config.get("NUTRITIONIX_APP_ID") and config.get("NUTRITIONIX_API_KEY"):
            available.append("nutritionix")
        if config.get("POWERREVIEWS_API_KEY") and config.get("POWERREVIEWS_MERCHANT_ID"):
            available.append("powerreviews")
        if config.get("SPOTIFY_CLIENT_ID") and config.get("SPOTIFY_CLIENT_SECRET"):
            available.append("spotify_podcasts")
        if config.get("SERPAPI_API_KEY"):
            available.append("google_patents")
        if config.get("STAMPED_API_KEY") and config.get("STAMPED_STORE_HASH"):
            available.append("stamped_reviews")
    return available


def _deep_research_provider_credentials(provider: str, config: dict[str, Any]) -> bool:
    """Per-provider credential check. Direct API key OR OpenRouter fallback key suffices."""
    has_openrouter = bool(config.get("OPENROUTER_API_KEY"))
    if provider == "chatgpt_deep_research":
        return bool(config.get("OPENAI_API_KEY")) or has_openrouter
    if provider == "claude_research":
        return bool(config.get("ANTHROPIC_API_KEY")) or has_openrouter
    if provider == "gemini_deep_research":
        google_key = (
            config.get("GEMINI_API_KEY")
            or config.get("GOOGLE_API_KEY")
            or config.get("GOOGLE_GENAI_API_KEY")
        )
        return bool(google_key) or has_openrouter
    if provider == "grok_deepsearch":
        return bool(config.get("XAI_API_KEY")) or has_openrouter
    if provider == "openrouter_research":
        return has_openrouter
    return False


def diagnose(config: dict[str, Any], requested_sources: list[str] | None = None) -> dict[str, Any]:
    requested_sources = normalize_requested_sources(requested_sources)
    google_key = _google_key(config)
    x_status = env.get_x_source_status(config)
    native_web_backend = None
    if config.get("BRAVE_API_KEY"):
        native_web_backend = "brave"
    elif config.get("EXA_API_KEY"):
        native_web_backend = "exa"
    elif config.get("SERPER_API_KEY"):
        native_web_backend = "serper"
    elif config.get("PARALLEL_API_KEY"):
        native_web_backend = "parallel"
    providers_status = {
        "google": bool(google_key),
        "openai": bool(config.get("OPENAI_API_KEY")) and config.get("OPENAI_AUTH_STATUS") == env.AUTH_STATUS_OK,
        "anthropic": bool(config.get("ANTHROPIC_API_KEY")),
        "xai": bool(config.get("XAI_API_KEY")),
        "openrouter": bool(config.get("OPENROUTER_API_KEY")),
    }
    return {
        "providers": providers_status,
        "local_mode": not any(providers_status.values()),
        "reasoning_provider": (
            config.get("SIGNALSWEEP_REASONING_PROVIDER")
            or config.get("LAST30DAYS_REASONING_PROVIDER")
            or "auto"
        ).lower(),
        "x_backend": x_status["source"],
        "bird_installed": x_status["bird_installed"],
        "bird_authenticated": x_status["bird_authenticated"],
        "bird_username": x_status["bird_username"],
        "native_web_backend": native_web_backend,
        "has_scrapecreators": bool(config.get("SCRAPECREATORS_API_KEY")),
        "has_github": bool(config.get("GITHUB_TOKEN") or which("gh")),
        "public_apis_enabled": public_api.is_public_apis_enabled(config),
        "available_sources": available_sources(config, requested_sources),
    }


def run(
    *,
    topic: str,
    config: dict[str, Any],
    depth: str,
    requested_sources: list[str] | None = None,
    mock: bool = False,
    x_handle: str | None = None,
    x_related: list[str] | None = None,
    web_backend: str = "auto",
    external_plan: dict | None = None,
    subreddits: list[str] | None = None,
    tiktok_hashtags: list[str] | None = None,
    tiktok_creators: list[str] | None = None,
    ig_creators: list[str] | None = None,
    lookback_days: int = 30,
    github_user: str | None = None,
    github_repos: list[str] | None = None,
    internal_subrun: bool = False,
) -> schema.Report:
    settings = DEPTH_SETTINGS[depth]
    requested_sources = normalize_requested_sources(requested_sources)
    from_date, to_date = dates.get_date_range(lookback_days)

    if mock:
        runtime = providers.mock_runtime(config, depth)
        reasoning_provider = None
        available = list(requested_sources or MOCK_AVAILABLE_SOURCES)
    else:
        runtime, reasoning_provider = providers.resolve_runtime(config, depth)
        available = available_sources(config, requested_sources)
        if requested_sources:
            available = [source for source in available if source in requested_sources]
    if web_backend == "none":
        available = [s for s in available if s != "grounding"]
    elif web_backend in ("brave", "exa", "serper", "parallel") and "grounding" not in available:
        available.append("grounding")
    if not available:
        raise RuntimeError("No sources are available for this run.")

    if external_plan:
        # External plan provided (e.g., from Claude Code via --plan flag).
        # Parse it through the same sanitizer to validate structure.
        plan = planner._sanitize_plan(
            external_plan, topic, available, requested_sources, depth,
        )
        plan_source = "external"
    else:
        plan = planner.plan_query(
            topic=topic,
            available_sources=available,
            requested_sources=requested_sources,
            depth=depth,
            provider=None if mock else reasoning_provider,
            model=None if mock else runtime.planner_model,
            context=config.get("_auto_resolve_context", ""),
            internal_subrun=internal_subrun,
        )
        if any("fallback" in note or "deterministic" in note for note in (plan.notes or [])):
            plan_source = "deterministic"
        elif not mock and reasoning_provider and runtime.planner_model:
            plan_source = "llm"
        else:
            plan_source = "deterministic"

    # Safety net: ensure grounding appears in all subqueries even if the planner
    # omits it. This is redundant when the planner includes grounding via
    # SOURCE_CAPABILITIES, but kept as a fallback.
    if web_backend != "none" and "grounding" in available:
        for sq in plan.subqueries:
            if "grounding" not in sq.sources:
                sq.sources.append("grounding")

    # Dark-demand query expansion: inject friction/absence/workaround subqueries.
    if query_expand.is_dark_demand_enabled(config):
        plan = query_expand.inject_into_plan(plan, topic, depth, available)

    print(
        f"[Planner] Plan: intent={plan.intent}, freshness={plan.freshness_mode}, "
        f"cluster_mode={plan.cluster_mode}, subqueries={len(plan.subqueries)}, "
        f"source={plan_source}",
        file=sys.stderr,
    )
    if plan.subqueries:
        for index, sq in enumerate(plan.subqueries, start=1):
            sources_str = ",".join(sq.sources) if sq.sources else "(none)"
            print(
                f"[Planner]   sq{index} label={sq.label} "
                f'search="{sq.search_query}" sources=[{sources_str}]',
                file=sys.stderr,
            )
    else:
        print("[Planner]   (no subqueries in plan)", file=sys.stderr)

    bundle = schema.RetrievalBundle(artifacts={"grounding": []})
    bundle.artifacts["plan_source"] = plan_source

    # Project-mode or person-mode GitHub: run once before the main subquery loop
    _github_custom_done = False
    _github_enriched_repos: set[str] = set()

    # Project mode takes priority over person mode
    if github_repos and "github" in available:
        try:
            project_items = github.search_github_project(
                github_repos, from_date, to_date,
                depth=depth, token=config.get("GITHUB_TOKEN"),
            )
            if project_items:
                normalized = _normalize_score_dedupe(
                    "github", project_items, from_date, to_date,
                    freshness_mode=plan.freshness_mode,
                    ranking_query=f"What are {', '.join(github_repos)} doing on GitHub?",
                )
                primary_label = plan.subqueries[0].label if plan.subqueries else "primary"
                bundle.add_items(primary_label, "github", normalized)
                _github_custom_done = True
                _github_enriched_repos = {r.lower() for r in github_repos}
        except Exception as exc:
            bundle.errors_by_source["github"] = f"Project-mode failed: {exc}"

    _github_person_done = False
    if github_user and "github" in available and not _github_custom_done:
        try:
            person_items = github.search_github_person(
                github_user, from_date, to_date,
                depth=depth, token=config.get("GITHUB_TOKEN"),
            )
            if person_items:
                normalized = _normalize_score_dedupe(
                    "github", person_items, from_date, to_date,
                    freshness_mode=plan.freshness_mode,
                    ranking_query=f"What is @{github_user} doing on GitHub?",
                )
                # Use the first subquery's label so RRF can look up the weight
                primary_label = plan.subqueries[0].label if plan.subqueries else "primary"
                bundle.add_items(primary_label, "github", normalized)
                _github_person_done = True
        except Exception as exc:
            bundle.errors_by_source["github"] = f"Person-mode failed: {exc}"

    # Thread-safe set prevents redundant fetches after a source returns 429
    rate_limited_sources: set[str] = set()
    rate_limit_lock = threading.Lock()

    futures = {}
    # Per-source fetch budget prevents redundant API calls
    source_fetch_count: dict[str, int] = {}
    stream_count = sum(
        1
        for subquery in plan.subqueries
        for source in subquery.sources
        if source in available
    )
    max_workers = max(4, min(16, stream_count or 1))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for subquery in plan.subqueries:
            for source in subquery.sources:
                if source not in available:
                    continue
                # Skip GitHub keyword search if person-mode already ran
                if source == "github" and (_github_person_done or _github_custom_done):
                    continue
                # Enforce per-source fetch cap
                cap = MAX_SOURCE_FETCHES.get(source)
                if cap is not None:
                    current = source_fetch_count.get(source, 0)
                    if current >= cap:
                        continue
                    source_fetch_count[source] = current + 1
                futures[
                    executor.submit(
                        _retrieve_stream,
                        topic=topic,
                        subquery=subquery,
                        source=source,
                        config=config,
                        depth=depth,
                        date_range=(from_date, to_date),
                        runtime=runtime,
                        mock=mock,
                        rate_limited_sources=rate_limited_sources,
                        rate_limit_lock=rate_limit_lock,
                        web_backend=web_backend,
                        raw_topic=topic,
                        subreddits=subreddits,
                        tiktok_hashtags=tiktok_hashtags,
                        tiktok_creators=tiktok_creators,
                        ig_creators=ig_creators,
                    )
                ] = (subquery, source)

        for future in as_completed(futures):
            subquery, source = futures[future]
            try:
                raw_items, artifact = future.result()
            except Exception as exc:
                # Share 429 signal so pending futures skip this source
                if _is_rate_limit_error(exc):
                    with rate_limit_lock:
                        rate_limited_sources.add(source)
                    bundle.errors_by_source[source] = str(exc)
                    continue
                # Retry once for transient 5xx errors
                if _is_transient_error(exc):
                    time.sleep(3)
                    try:
                        raw_items, artifact = _retrieve_stream(
                            topic=topic, subquery=subquery, source=source,
                            config=config, depth=depth, date_range=(from_date, to_date),
                            runtime=runtime, mock=mock,
                            rate_limited_sources=rate_limited_sources,
                            rate_limit_lock=rate_limit_lock,
                            web_backend=web_backend,
                            raw_topic=topic,
                            subreddits=subreddits,
                            tiktok_hashtags=tiktok_hashtags,
                            tiktok_creators=tiktok_creators,
                            ig_creators=ig_creators,
                        )
                    except Exception as retry_exc:
                        bundle.errors_by_source[source] = f"{exc} (retried once, still failed: {retry_exc})"
                        continue
                else:
                    bundle.errors_by_source[source] = str(exc)
                    continue
            normalized = _normalize_score_dedupe(
                source, raw_items, from_date, to_date,
                freshness_mode=plan.freshness_mode,
                ranking_query=subquery.ranking_query,
            )
            normalized = normalized[: settings["per_stream_limit"]]
            bundle.add_items(subquery.label, source, normalized)
            if artifact:
                bundle.artifacts.setdefault("grounding", []).append(artifact)

    # Phase 2: supplemental entity-based searches
    _run_supplemental_searches(
        topic=topic,
        bundle=bundle,
        plan=plan,
        config=config,
        depth=depth,
        date_range=(from_date, to_date),
        runtime=runtime,
        mock=mock,
        rate_limited_sources=rate_limited_sources,
        rate_limit_lock=rate_limit_lock,
        x_handle=x_handle,
        x_related=x_related,
    )

    # Phase 2b: retry thin sources with simplified query
    # Note: _github_skip_sources tells the retry to not re-run GitHub keyword search
    # when project-mode or person-mode already provided authoritative data.
    _github_skip_retry = {"github"} if (_github_person_done or _github_custom_done) else set()
    _retry_thin_sources(
        topic=topic,
        bundle=bundle,
        plan=plan,
        config=config,
        depth=depth,
        date_range=(from_date, to_date),
        runtime=runtime,
        mock=mock,
        rate_limited_sources=rate_limited_sources,
        rate_limit_lock=rate_limit_lock,
        settings=settings,
        web_backend=web_backend,
        skip_sources=_github_skip_retry,
    )

    # Clear errors for sources that returned items despite partial failures.
    # A source that 429'd on one subquery but succeeded on another is not "errored".
    for source in list(bundle.errors_by_source):
        if bundle.items_by_source.get(source):
            del bundle.errors_by_source[source]

    items_by_source = _finalize_items_by_source(bundle.items_by_source, topic=topic, config=config)
    candidates = weighted_rrf(bundle.items_by_source_and_query, plan, pool_limit=settings["pool_limit"])
    ranked_candidates = rerank.rerank_candidates(
        topic=topic,
        plan=plan,
        candidates=candidates,
        provider=None if mock else reasoning_provider,
        model=None if mock else runtime.rerank_model,
        shortlist_size=settings["rerank_limit"],
    )
    rerank.score_fun(
        topic=topic,
        candidates=ranked_candidates,
        provider=None if mock else reasoning_provider,
        model=None if mock else runtime.rerank_model,
    )

    # Phase 3: post-rerank GitHub star enrichment
    if "github" in available and not mock:
        github.enrich_candidates_with_stars(
            ranked_candidates,
            token=config.get("GITHUB_TOKEN"),
            already_enriched=_github_enriched_repos,
        )

    clusters = cluster_candidates(ranked_candidates, plan)
    warnings = _warnings(items_by_source, ranked_candidates, bundle.errors_by_source)

    return schema.Report(
        topic=topic,
        range_from=from_date,
        range_to=to_date,
        generated_at=datetime.now(timezone.utc).isoformat(),
        provider_runtime=runtime,
        query_plan=plan,
        clusters=clusters,
        ranked_candidates=ranked_candidates,
        items_by_source=items_by_source,
        errors_by_source=bundle.errors_by_source,
        warnings=warnings,
        artifacts=bundle.artifacts,
    )


def _normalize_score_dedupe(
    source: str,
    raw_items: list[dict],
    from_date: str,
    to_date: str,
    freshness_mode: str,
    ranking_query: str,
) -> list[schema.SourceItem]:
    """Normalize, annotate, prune, dedupe, and extract snippets for a batch of raw items."""
    normalized = normalize.normalize_source_items(
        source, raw_items, from_date, to_date,
        freshness_mode=freshness_mode,
    )
    prepared_query = relevance.PreparedQuery(ranking_query)
    normalized = signals.annotate_stream(normalized, prepared_query, freshness_mode)
    normalized = signals.prune_low_relevance(normalized)
    normalized = dedupe.dedupe_items(normalized)
    for item in normalized:
        item.snippet = snippet.extract_best_snippet(item, prepared_query)
    return normalized


def _finalize_items_by_source(
    items_by_source_raw: dict[str, list[schema.SourceItem]],
    topic: str = "",
    config: dict | None = None,
) -> dict[str, list[schema.SourceItem]]:
    finalized = {}
    for source, items in items_by_source_raw.items():
        items = sorted(items, key=lambda item: item.local_rank_score or 0.0, reverse=True)
        items = dedupe.dedupe_items(items)
        if source == "polymarket" and topic:
            items = polymarket.filter_items_against_topic(topic, items)
            keywords = config.get("_polymarket_keywords") if isinstance(config, dict) else None
            if keywords:
                items = polymarket.filter_items_against_keywords(items, keywords)
        if source == "digg" and items:
            digg.enrich_source_items(items, top_k=3)
        finalized[source] = items
    return finalized


def _warnings(
    items_by_source: dict[str, list[schema.SourceItem]],
    candidates: list[schema.Candidate],
    errors_by_source: dict[str, str],
) -> list[str]:
    warnings: list[str] = []
    if not candidates:
        warnings.append("No candidates survived retrieval and ranking.")
    if len(candidates) < 5:
        warnings.append("Evidence is thin for this topic.")
    top_sources = {
        source
        for candidate in candidates[:5]
        for source in schema.candidate_sources(candidate)
    }
    if len(top_sources) <= 1 and len(candidates) >= 3:
        warnings.append("Top evidence is highly concentrated in one source.")
    if errors_by_source:
        warnings.append(f"Some sources failed: {', '.join(sorted(errors_by_source))}")
    if not items_by_source:
        warnings.append("No source returned usable items.")
    return warnings


def _is_rate_limit_error(exc: Exception) -> bool:
    """Detect 429 rate-limit errors by status code or message text."""
    if hasattr(exc, "status_code") and getattr(exc, "status_code", None) == 429:
        return True
    return "429" in str(exc)


def _is_transient_error(exc: Exception) -> bool:
    """Detect 5xx server errors that are worth retrying."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and 500 <= status < 600:
        return True
    msg = str(exc)
    return any(code in msg for code in ("500", "502", "503", "504"))


def _run_supplemental_searches(
    *,
    topic: str,
    bundle: schema.RetrievalBundle,
    plan: schema.QueryPlan,
    config: dict[str, Any],
    depth: str,
    date_range: tuple[str, str],
    runtime: schema.ProviderRuntime,
    mock: bool,
    rate_limited_sources: set[str],
    rate_limit_lock: threading.Lock,
    x_handle: str | None = None,
    x_related: list[str] | None = None,
) -> None:
    """Phase 2: extract entities from Phase 1 results, run targeted supplemental searches."""
    if depth == "quick" or mock:
        return

    from_date, to_date = date_range

    # Convert SourceItems to dicts for entity_extract
    x_dicts = [
        {"author_handle": item.author or "", "text": item.body or ""}
        for item in bundle.items_by_source.get("x", [])
    ]
    reddit_dicts = [
        {
            "subreddit": item.container or "",
            "comment_insights": item.metadata.get("comment_insights", []),
            "top_comments": [
                {"excerpt": c.get("excerpt", c.get("text", ""))}
                for c in (item.metadata.get("top_comments") or [])
                if isinstance(c, dict)
            ],
        }
        for item in bundle.items_by_source.get("reddit", [])
    ]

    if not x_dicts and not reddit_dicts and not x_handle and not x_related:
        return

    entities = entity_extract.extract_entities(
        reddit_dicts, x_dicts,
        max_handles=3, max_subreddits=3,
    )

    handles = entities.get("x_handles", [])

    # Add explicit --x-handle if provided
    if x_handle:
        handle_clean = x_handle.lstrip("@").lower()
        if handle_clean not in [h.lower() for h in handles]:
            handles.insert(0, handle_clean)

    # Collect related handles (searched separately with lower weight)
    related_handles = []
    if x_related:
        primary_lower = x_handle.lstrip("@").lower() if x_handle else ""
        for rh in x_related:
            rh_clean = rh.lstrip("@").lower().strip()
            if rh_clean and rh_clean != primary_lower and rh_clean not in [h.lower() for h in handles]:
                related_handles.append(rh_clean)

    if not handles and not related_handles:
        return

    # Check if X is rate-limited
    if "x" in rate_limited_sources:
        return

    backend = runtime.x_search_backend or env.get_x_source(config)
    if backend != "bird":
        return  # Handle search only works with Bird CLI

    # Collect existing URLs for deduplication
    existing_urls = {
        item.url
        for items in bundle.items_by_source.values()
        for item in items
        if item.url
    }

    ranking_query = plan.subqueries[0].ranking_query if plan.subqueries else topic
    primary_label = plan.subqueries[0].label if plan.subqueries else "primary"

    # Search primary handles (full weight)
    if handles:
        try:
            raw_items = bird_x.search_handles(
                handles, topic, from_date, count_per=3,
            )
        except Exception as exc:
            print(f"[Pipeline] Phase 2 handle search failed: {exc}", file=sys.stderr)
            if not bundle.items_by_source.get("x"):
                bundle.errors_by_source["x"] = f"Phase 2 handle search: {exc}"
            raw_items = []

        if raw_items:
            normalized = _normalize_score_dedupe(
                "x", raw_items, from_date, to_date,
                freshness_mode=plan.freshness_mode,
                ranking_query=ranking_query,
            )
            # Deduplicate against Phase 1 URLs
            normalized = [item for item in normalized if item.url not in existing_urls]
            if normalized:
                bundle.add_items(primary_label, "x", normalized)
                # Update existing URLs for related-handle dedup
                for item in normalized:
                    if item.url:
                        existing_urls.add(item.url)

    # Search related handles with lower weight (0.3)
    if related_handles:
        try:
            raw_items = bird_x.search_handles(
                related_handles, topic, from_date, count_per=3,
            )
        except Exception as exc:
            print(f"[Pipeline] Phase 2 related handle search failed: {exc}", file=sys.stderr)
            raw_items = []

        if raw_items:
            normalized = _normalize_score_dedupe(
                "x", raw_items, from_date, to_date,
                freshness_mode=plan.freshness_mode,
                ranking_query=ranking_query,
            )
            # Deduplicate against all existing URLs (Phase 1 + primary handles)
            normalized = [item for item in normalized if item.url not in existing_urls]
            if normalized:
                # Use a separate subquery label with lower weight so RRF
                # scores related-handle results below primary results.
                bundle.add_items("supplemental-related", "x", normalized)
                # Register the supplemental-related label in the plan for fusion
                if not any(sq.label == "supplemental-related" for sq in plan.subqueries):
                    plan.subqueries.append(
                        schema.SubQuery(
                            label="supplemental-related",
                            search_query=", ".join(related_handles),
                            ranking_query=ranking_query,
                            sources=["x"],
                            weight=0.3,
                        )
                    )


def _retry_thin_sources(
    *,
    topic: str,
    bundle: schema.RetrievalBundle,
    plan: schema.QueryPlan,
    config: dict[str, Any],
    depth: str,
    date_range: tuple[str, str],
    runtime: schema.ProviderRuntime,
    mock: bool,
    rate_limited_sources: set[str],
    rate_limit_lock: threading.Lock,
    settings: dict[str, Any],
    web_backend: str = "auto",
    skip_sources: set[str] | None = None,
) -> None:
    """Retry sources with thin results using simplified core subject query."""
    if depth == "quick":
        return

    planned_sources: list[str] = []
    for subquery in plan.subqueries:
        for source in subquery.sources:
            if source not in planned_sources:
                planned_sources.append(source)
    _skip = skip_sources or set()
    thin_sources = [
        source
        for source in planned_sources
        if len(bundle.items_by_source.get(source, [])) < 3
        and source not in bundle.errors_by_source
        and source not in _skip
    ]

    if not thin_sources:
        return

    core = query.extract_core_subject(topic, max_words=3)
    if not core:
        return
    # Note: we intentionally do NOT skip when core == topic. For short topics
    # like "Kanye West", the 3-word core IS the topic — but the planner may
    # have sent a different (worse) query to the source. Retrying with the
    # raw core subject is still valuable.

    from_date, to_date = date_range

    # Create a retry subquery with the simplified core subject
    retry_subquery = schema.SubQuery(
        label="retry",
        search_query=core,
        ranking_query=f"What recent evidence from the last 30 days matters for {core}?",
        sources=thin_sources,
        weight=0.3,
    )

    def _retry_one_source(source: str) -> tuple[str, list[schema.SourceItem]]:
        raw_items, _artifact = _retrieve_stream(
            topic=topic,
            subquery=retry_subquery,
            source=source,
            config=config,
            depth=depth,
            date_range=date_range,
            runtime=runtime,
            mock=mock,
            rate_limited_sources=rate_limited_sources,
            rate_limit_lock=rate_limit_lock,
            web_backend=web_backend,
            raw_topic=topic,
        )
        normalized = _normalize_score_dedupe(
            source,
            raw_items,
            from_date,
            to_date,
            freshness_mode=plan.freshness_mode,
            ranking_query=retry_subquery.ranking_query,
        )
        return source, normalized[:settings["per_stream_limit"]]

    retryable = [s for s in thin_sources if s not in rate_limited_sources]

    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=min(4, len(retryable) or 1)) as executor:
        futures = {executor.submit(_retry_one_source, s): s for s in retryable}
        for future in as_completed(futures):
            source = futures[future]
            try:
                source, normalized = future.result()
                existing_urls = {item.url for item in bundle.items_by_source.get(source, []) if item.url}
                new_items = [item for item in normalized if item.url not in existing_urls]

                if new_items:
                    bundle.items_by_source.setdefault(source, []).extend(new_items)
                    primary_label = plan.subqueries[0].label if plan.subqueries else "primary"
                    bundle.items_by_source_and_query.setdefault((primary_label, source), []).extend(new_items)
            except Exception as exc:
                print(f"[Pipeline] Retry failed for {source}: {type(exc).__name__}: {exc}", file=sys.stderr)


def _retrieve_stream(
    *,
    topic: str,
    subquery: schema.SubQuery,
    source: str,
    config: dict[str, Any],
    depth: str,
    date_range: tuple[str, str],
    runtime: schema.ProviderRuntime,
    mock: bool,
    rate_limited_sources: set[str] | None = None,
    rate_limit_lock: threading.Lock | None = None,
    web_backend: str = "auto",
    raw_topic: str = "",
    subreddits: list[str] | None = None,
    tiktok_hashtags: list[str] | None = None,
    tiktok_creators: list[str] | None = None,
    ig_creators: list[str] | None = None,
) -> tuple[list[dict], dict]:
    # Early exit if source was rate-limited by a sibling future
    if rate_limited_sources is not None and source in rate_limited_sources:
        return [], {}
    from_date, to_date = date_range
    if mock:
        return _mock_stream_results(source, subquery)
    if source == "grounding":
        return grounding.web_search(
            subquery.search_query, date_range, config, backend=web_backend)
    if source == "reddit":
        # Use raw_topic so expand_reddit_queries() generates diverse variants
        # from the original user topic, not the planner's narrowed search_query.
        reddit_query = raw_topic or subquery.search_query
        # Public Reddit first (free, gets comments); SC as backup
        try:
            public_results = reddit_public.search_reddit_public(
                reddit_query, from_date, to_date, depth=depth,
                subreddits=subreddits,
            )
            if public_results:
                return public_results, {}
        except Exception as exc:
            sys.stderr.write(
                f"[Reddit] Public search failed ({type(exc).__name__}: {exc})"
            )
            if not paid_api.is_paid_apis_enabled(config) or not config.get("SCRAPECREATORS_API_KEY"):
                sys.stderr.write("\n")
                return [], {}
            sys.stderr.write(", using ScrapeCreators backup\n")
        # Fallback to ScrapeCreators if public returned empty or raised
        if paid_api.is_paid_apis_enabled(config) and config.get("SCRAPECREATORS_API_KEY"):
            try:
                result = reddit.search_and_enrich(
                    reddit_query,
                    from_date,
                    to_date,
                    depth=depth,
                    token=config.get("SCRAPECREATORS_API_KEY"),
                    subreddits=subreddits,
                )
                return reddit.parse_reddit_response(result), {}
            except Exception as exc:
                sys.stderr.write(
                    f"[Reddit] ScrapeCreators backup also failed "
                    f"({type(exc).__name__}: {exc})\n"
                )
        return [], {}
    if source == "x":
        backend = runtime.x_search_backend or env.get_x_source(config)
        if backend == "bird":
            result = bird_x.search_x(subquery.search_query, from_date, to_date, depth=depth)
            return bird_x.parse_bird_response(result, query=subquery.search_query), {}
        if backend == "xai":
            model = config.get("LAST30DAYS_X_MODEL") or config.get("XAI_MODEL_PIN") or providers.XAI_DEFAULT
            result = xai_x.search_x(
                config["XAI_API_KEY"],
                model,
                subquery.search_query,
                from_date,
                to_date,
                depth=depth,
            )
            return xai_x.parse_x_response(result), {}
        if backend == "xurl":
            result = xurl_x.search_x(subquery.search_query, depth=depth)
            return xurl_x.parse_x_response(result, topic=subquery.search_query), {}
        raise RuntimeError("No X backend is available.")
    if source == "youtube":
        # Use raw_topic so expand_youtube_queries() generates diverse variants
        # from the original user topic, not the planner's narrowed search_query.
        yt_query = raw_topic or subquery.search_query
        result = None
        # Try yt-dlp first, fall back to SC YouTube if it fails or isn't installed
        if which("yt-dlp"):
            try:
                result = youtube_yt.search_and_transcribe(yt_query, from_date, to_date, depth=depth)
            except Exception:
                result = None
        if (
            (result is None or not result.get("items"))
            and paid_api.is_paid_apis_enabled(config)
            and env.is_youtube_sc_available(config)
        ):
            sc_token = config.get("SCRAPECREATORS_API_KEY", "")
            result = youtube_yt.search_youtube_sc(yt_query, from_date, to_date, depth=depth, token=sc_token)
        if result is None:
            result = {"items": []}
        # Enrich top videos with comments when SC key is available
        items = youtube_yt.parse_youtube_response(result)
        if items and paid_api.is_paid_apis_enabled(config) and env.is_youtube_comments_available(config):
            sc_token = config.get("SCRAPECREATORS_API_KEY", "")
            youtube_yt.enrich_with_comments(items, token=sc_token)
        return items, {}
    if source == "tiktok":
        # Use raw_topic so expand_tiktok_queries() generates diverse variants
        # from the original user topic, not the planner's narrowed search_query.
        tiktok_query = raw_topic or subquery.search_query
        result = tiktok.search_and_enrich(
            tiktok_query,
            from_date,
            to_date,
            depth=depth,
            token=env.get_tiktok_token(config),
            hashtags=tiktok_hashtags,
            creators=tiktok_creators,
        )
        items = tiktok.parse_tiktok_response(result)
        if items and env.is_tiktok_comments_available(config):
            sc_token = config.get("SCRAPECREATORS_API_KEY", "")
            tiktok.enrich_with_comments(items, token=sc_token)
        return items, {}
    if source == "instagram":
        # Use raw_topic so expand_instagram_queries() generates diverse variants
        # from the original user topic, not the planner's narrowed search_query.
        ig_query = raw_topic or subquery.search_query
        result = instagram.search_and_enrich(
            ig_query,
            from_date,
            to_date,
            depth=depth,
            token=env.get_instagram_token(config),
            ig_creators=ig_creators,
        )
        return instagram.parse_instagram_response(result), {}
    if source == "hackernews":
        result = hackernews.search_hackernews(subquery.search_query, from_date, to_date, depth=depth)
        return hackernews.parse_hackernews_response(result, query=subquery.search_query), {}
    if source == "digg":
        result = digg.search_digg(subquery.search_query, from_date, to_date, depth=depth, config=config)
        items = digg.parse_digg_response(result, query=subquery.search_query)
        return items, {}
    if source == "bluesky":
        result = bluesky.search_bluesky(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return bluesky.parse_bluesky_response(result), {}
    if source == "threads":
        result = threads.search_threads(
            subquery.search_query, from_date, to_date,
            depth=depth,
            token=config.get("SCRAPECREATORS_API_KEY"),
        )
        return threads.parse_threads_response(result), {}
    if source == "truthsocial":
        result = truthsocial.search_truthsocial(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return truthsocial.parse_truthsocial_response(result), {}
    if source == "polymarket":
        result = polymarket.search_polymarket(subquery.search_query, from_date, to_date, depth=depth)
        return polymarket.parse_polymarket_response(result, topic=subquery.search_query), {}
    if source == "github":
        result = github.search_github(subquery.search_query, from_date, to_date, depth=depth, token=config.get("GITHUB_TOKEN"))
        return result, {}
    if source == "pinterest":
        result = pinterest.search_pinterest(
            subquery.search_query, from_date, to_date,
            depth=depth,
            token=env.get_pinterest_token(config),
        )
        return pinterest.parse_pinterest_response(result), {}
    if source == "xiaohongshu":
        return xiaohongshu_api.search_feeds(
            subquery.search_query,
            from_date,
            to_date,
            env.get_xiaohongshu_api_base(config),
            depth=depth,
        ), {}
    if source == "perplexity":
        return perplexity.search(subquery.search_query, date_range, config, deep=config.get("_deep_research", False))
    if source == "xquik":
        result = xquik.search_xquik(
            subquery.search_query, from_date, to_date,
            depth=depth,
            token=env.get_xquik_token(config),
        )
        return xquik.parse_xquik_response(result), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.5)
    # ---------------------------------------------------------------------
    if source == "linkedin":
        result = linkedin.search_linkedin(
            subquery.search_query, from_date, to_date,
            depth=depth,
            api_key=config.get("SCRAPECREATORS_API_KEY", ""),
        )
        return linkedin.parse_linkedin_response(result, query=subquery.search_query), {}
    if source == "stackoverflow":
        result = stackoverflow.search_stackoverflow(
            subquery.search_query, from_date, to_date, depth=depth,
        )
        return stackoverflow.parse_stackoverflow_response(result, query=subquery.search_query), {}
    if source == "rss_blogs":
        result = rss_blogs.search_rss_blogs(
            subquery.search_query, from_date, to_date, depth=depth,
        )
        return rss_blogs.parse_rss_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date,
        ), {}
    if source == "podcasts":
        result = podcasts.search_and_enrich(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return podcasts.parse_podcast_response(result), {}
    if source == "producthunt":
        result = producthunt.search_producthunt(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return producthunt.parse_producthunt_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date,
        ), {}
    if source == "x_sc":
        result = scrapecreators_x.search_x(
            subquery.search_query, from_date, to_date,
            depth=depth,
            token=config.get("SCRAPECREATORS_API_KEY"),
        )
        return scrapecreators_x.parse_x_response(result), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.6 — Free/Public Data)
    # ---------------------------------------------------------------------
    if source == "sec_edgar":
        result = sec_edgar.search_sec_edgar(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return sec_edgar.parse_sec_edgar_response(result, query=subquery.search_query), {}
    if source == "arxiv":
        result = arxiv.search_arxiv(subquery.search_query, from_date, to_date, depth=depth)
        return arxiv.parse_arxiv_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date,
        ), {}
    if source == "biorxiv":
        result = biorxiv.search_biorxiv(subquery.search_query, from_date, to_date, depth=depth)
        return biorxiv.parse_biorxiv_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "medrxiv":
        result = medrxiv.search_medrxiv(subquery.search_query, from_date, to_date, depth=depth)
        return medrxiv.parse_medrxiv_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "semantic_scholar":
        result = semantic_scholar.search_semantic_scholar(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return semantic_scholar.parse_semantic_scholar_response(result, query=subquery.search_query), {}
    if source == "openalex":
        result = openalex.search_openalex(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return openalex.parse_openalex_response(result, query=subquery.search_query), {}
    if source == "pubmed":
        result = pubmed.search_pubmed(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return pubmed.parse_pubmed_response(result, query=subquery.search_query), {}
    if source == "datagov":
        result = datagov.search_datagov(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return datagov.parse_datagov_response(result, query=subquery.search_query), {}
    if source == "bls":
        result = bls.search_bls(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return bls.parse_bls_response(result, query=subquery.search_query), {}
    if source == "worldbank":
        result = worldbank.search_worldbank(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return worldbank.parse_worldbank_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "eurostat":
        result = eurostat.search_eurostat(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return eurostat.parse_eurostat_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "wiki_pageviews":
        result = wiki_pageviews.search_wiki_pageviews(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return wiki_pageviews.parse_wiki_pageviews_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date,
        ), {}
    if source == "wiki_recent_changes":
        result = wiki_recent_changes.search_wiki_recent_changes(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return wiki_recent_changes.parse_wiki_recent_changes_response(result, query=subquery.search_query), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.6.1 — public-data backlog)
    # ---------------------------------------------------------------------
    if source == "uk_ons":
        result = uk_ons.search_uk_ons(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return uk_ons.parse_uk_ons_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "imf":
        result = imf.search_imf(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return imf.parse_imf_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "crossref":
        result = crossref.search_crossref(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return crossref.parse_crossref_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "orcid":
        result = orcid.search_orcid(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return orcid.parse_orcid_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "bea":
        result = bea.search_bea(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return bea.parse_bea_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "usda_nass":
        result = usda_nass.search_usda_nass(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return usda_nass.parse_usda_nass_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "wikidata":
        result = wikidata.search_wikidata(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return wikidata.parse_wikidata_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "pubmed_efetch":
        result = pubmed.search_pubmed_efetch(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return pubmed.parse_pubmed_efetch_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.7 — Amazon/ecommerce intelligence)
    # ---------------------------------------------------------------------
    if source == "keepa":
        result = keepa.search_keepa(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return keepa.parse_keepa_response(result, query=subquery.search_query), {}
    if source == "helium10":
        result = helium10.search_helium10(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return helium10.parse_helium10_response(result, query=subquery.search_query), {}
    if source == "junglescout":
        result = junglescout.search_junglescout(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return junglescout.parse_junglescout_response(result, query=subquery.search_query), {}
    if source == "datadive":
        result = datadive.search_datadive(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return datadive.parse_datadive_response(result, query=subquery.search_query), {}
    if source == "smartscout":
        result = smartscout.search_smartscout(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return smartscout.parse_smartscout_response(result, query=subquery.search_query), {}
    if source == "amazon_reviews":
        result = amazon_reviews.search_amazon_reviews(
            subquery.search_query, from_date, to_date, depth=depth,
            api_key=config.get("SCRAPECREATORS_API_KEY") or "",
        )
        return amazon_reviews.parse_amazon_reviews_response(result, query=subquery.search_query), {}
    if source == "tiktok_shop":
        result = tiktok_shop.search_tiktok_shop(
            subquery.search_query, from_date, to_date, depth=depth,
            api_key=config.get("SCRAPECREATORS_API_KEY") or "",
        )
        return tiktok_shop.parse_tiktok_shop_response(result, query=subquery.search_query), {}
    if source == "sp_api":
        result = sp_api.search_sp_api(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return sp_api.parse_sp_api_response(result, query=subquery.search_query), {}
    if source == "ads_api":
        result = ads_api.search_ads_api(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return ads_api.parse_ads_api_response(result, query=subquery.search_query), {}
    if source == "google_shopping":
        result = google_shopping.search_google_shopping(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return google_shopping.parse_google_shopping_response(result, query=subquery.search_query), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.8 — Deep Research LLM providers)
    # Logs cost estimate to stderr before invocation; existing pipeline executor
    # already runs sources in parallel (max 16 workers), so multi-provider
    # deep-research runs concurrently without separate orchestration.
    # ---------------------------------------------------------------------
    # v3.8.1: each branch is wrapped in cached_provider_call. log_invocation
    # moves inside the closure so cache hits don't print the cost line (cache
    # hits print "Cache hit (age: Xh)" instead via cached_provider_call).
    if source == "chatgpt_deep_research":
        def _chatgpt_call():
            deep_research.log_invocation("chatgpt_deep_research")
            result = chatgpt_deep_research.search_chatgpt_deep_research(
                subquery.search_query, from_date, to_date, depth=depth, config=config,
            )
            return chatgpt_deep_research.parse_chatgpt_deep_research_response(
                result, query=subquery.search_query,
            ), {}
        return deep_research.cached_provider_call(
            "chatgpt_deep_research", subquery.search_query,
            from_date, to_date, depth, _chatgpt_call, config,
        )
    if source == "claude_research":
        def _claude_call():
            deep_research.log_invocation("claude_research")
            result = claude_research.search_claude_research(
                subquery.search_query, from_date, to_date, depth=depth, config=config,
            )
            return claude_research.parse_claude_research_response(
                result, query=subquery.search_query,
            ), {}
        return deep_research.cached_provider_call(
            "claude_research", subquery.search_query,
            from_date, to_date, depth, _claude_call, config,
        )
    if source == "gemini_deep_research":
        def _gemini_call():
            deep_research.log_invocation("gemini_deep_research")
            result = gemini_deep_research.search_gemini_deep_research(
                subquery.search_query, from_date, to_date, depth=depth, config=config,
            )
            return gemini_deep_research.parse_gemini_deep_research_response(
                result, query=subquery.search_query,
            ), {}
        return deep_research.cached_provider_call(
            "gemini_deep_research", subquery.search_query,
            from_date, to_date, depth, _gemini_call, config,
        )
    if source == "grok_deepsearch":
        def _grok_call():
            deep_research.log_invocation("grok_deepsearch")
            result = grok_deepsearch.search_grok_deepsearch(
                subquery.search_query, from_date, to_date, depth=depth, config=config,
            )
            return grok_deepsearch.parse_grok_deepsearch_response(
                result, query=subquery.search_query,
            ), {}
        return deep_research.cached_provider_call(
            "grok_deepsearch", subquery.search_query,
            from_date, to_date, depth, _grok_call, config,
        )
    if source == "openrouter_research":
        def _openrouter_call():
            deep_research.log_invocation("openrouter_research")
            result = openrouter_research.search_openrouter_research(
                subquery.search_query, from_date, to_date, depth=depth, config=config,
            )
            return openrouter_research.parse_openrouter_research_response(
                result, query=subquery.search_query,
            ), {}
        return deep_research.cached_provider_call(
            "openrouter_research", subquery.search_query,
            from_date, to_date, depth, _openrouter_call, config,
        )
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.9 — Demand signals)
    # ---------------------------------------------------------------------
    if source == "google_trends":
        result = google_trends.search_google_trends(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return google_trends.parse_google_trends_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "pinterest_trends":
        result = pinterest_trends.search_pinterest_trends(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return pinterest_trends.parse_pinterest_trends_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "tiktok_creative_center":
        result = tiktok_creative_center.search_tiktok_creative_center(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return tiktok_creative_center.parse_tiktok_creative_center_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "amazon_autocomplete":
        result = amazon_autocomplete.search_amazon_autocomplete(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return amazon_autocomplete.parse_amazon_autocomplete_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "youtube_trending":
        result = youtube_trending.search_youtube_trending(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return youtube_trending.parse_youtube_trending_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "soovle":
        result = soovle.search_soovle(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return soovle.parse_soovle_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "answer_socrates":
        result = answer_socrates.search_answer_socrates(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return answer_socrates.parse_answer_socrates_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "keyword_sheeter":
        result = keyword_sheeter.search_keyword_sheeter(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return keyword_sheeter.parse_keyword_sheeter_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "sparktoro":
        result = sparktoro.search_sparktoro(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return sparktoro.parse_sparktoro_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "exploding_topics":
        result = exploding_topics.search_exploding_topics(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return exploding_topics.parse_exploding_topics_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "answerthepublic":
        result = answerthepublic.search_answerthepublic(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return answerthepublic.parse_answerthepublic_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "alsoasked":
        result = alsoasked.search_alsoasked(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return alsoasked.parse_alsoasked_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "glimpse":
        result = glimpse.search_glimpse(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return glimpse.parse_glimpse_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.14 — Non-Amazon marketplaces)
    # ---------------------------------------------------------------------
    if source == "etsy":
        result = etsy.search_etsy(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return etsy.parse_etsy_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "pinterest_commerce":
        result = pinterest_commerce.search_pinterest_commerce(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return pinterest_commerce.parse_pinterest_commerce_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "amazon_vendor":
        result = amazon_vendor.search_amazon_vendor(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return amazon_vendor.parse_amazon_vendor_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "walmart_marketplace":
        result = walmart_marketplace.search_walmart_marketplace(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return walmart_marketplace.parse_walmart_marketplace_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "walmart_connect":
        result = walmart_connect.search_walmart_connect(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return walmart_connect.parse_walmart_connect_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "tiktok_shop_seller":
        result = tiktok_shop_seller.search_tiktok_shop_seller(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return tiktok_shop_seller.parse_tiktok_shop_seller_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.15 — Patents/Legal/Regulatory)
    # ---------------------------------------------------------------------
    if source == "federal_register":
        result = federal_register.search_federal_register(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return federal_register.parse_federal_register_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "fda_openfda":
        result = fda_openfda.search_fda_openfda(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return fda_openfda.parse_fda_openfda_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "courtlistener":
        result = courtlistener.search_courtlistener(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return courtlistener.parse_courtlistener_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "uspto_patents":
        result = uspto_patents.search_uspto_patents(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return uspto_patents.parse_uspto_patents_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "epo_ops":
        result = epo_ops.search_epo_ops(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return epo_ops.parse_epo_ops_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.16 — Meta Ad Library)
    # ---------------------------------------------------------------------
    if source == "meta_ad_library":
        result = meta_ad_library.search_meta_ad_library(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return meta_ad_library.parse_meta_ad_library_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.16.1 — Google Ads Transparency)
    # ---------------------------------------------------------------------
    if source == "google_ads_transparency":
        result = google_ads_transparency.search_google_ads_transparency(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return google_ads_transparency.parse_google_ads_transparency_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.16.2 — TikTok Ads Library)
    # ---------------------------------------------------------------------
    if source == "tiktok_ads_library":
        result = tiktok_ads_library.search_tiktok_ads_library(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return tiktok_ads_library.parse_tiktok_ads_library_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.16.3 — LinkedIn Ad Library)
    # ---------------------------------------------------------------------
    if source == "linkedin_ad_library":
        result = linkedin_ad_library.search_linkedin_ad_library(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return linkedin_ad_library.parse_linkedin_ad_library_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.16.4 — Wayback Machine CDX)
    # ---------------------------------------------------------------------
    if source == "wayback_machine_cdx":
        result = wayback_machine_cdx.search_wayback_machine_cdx(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return wayback_machine_cdx.parse_wayback_machine_cdx_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.17.0 — Review aggregation)
    # ---------------------------------------------------------------------
    if source == "app_store_reviews":
        result = app_store_reviews.search_app_store_reviews(
            subquery.search_query, from_date, to_date, config=config,
        )
        return app_store_reviews.parse_app_store_reviews_response(result), {}
    if source == "yelp_fusion":
        result = yelp_fusion.search_yelp_fusion(
            subquery.search_query, from_date, to_date, config=config,
        )
        return yelp_fusion.parse_yelp_fusion_response(result), {}
    if source == "trustpilot":
        result = trustpilot.search_trustpilot(
            subquery.search_query, from_date, to_date, config=config,
        )
        return trustpilot.parse_trustpilot_response(result), {}
    if source == "g2":
        result = g2.search_g2(
            subquery.search_query, from_date, to_date, config=config,
        )
        return g2.parse_g2_response(result), {}
    if source == "capterra":
        result = capterra.search_capterra(
            subquery.search_query, from_date, to_date, config=config,
        )
        return capterra.parse_capterra_response(result), {}
    if source == "google_play_reviews":
        result = google_play_reviews.search_google_play_reviews(
            subquery.search_query, from_date, to_date, config=config,
        )
        return google_play_reviews.parse_google_play_reviews_response(result), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.18.0 — Financial markets)
    # ---------------------------------------------------------------------
    if source == "fred":
        result = fred.search_fred(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return fred.parse_fred_response(result), {}
    if source == "alpha_vantage":
        result = alpha_vantage.search_alpha_vantage(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return alpha_vantage.parse_alpha_vantage_response(result), {}
    if source == "polygon_io":
        result = polygon_io.search_polygon_io(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return polygon_io.parse_polygon_io_response(result), {}
    if source == "finnhub":
        result = finnhub.search_finnhub(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return finnhub.parse_finnhub_response(result), {}
    if source == "sec_xbrl":
        result = sec_xbrl.search_sec_xbrl(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return sec_xbrl.parse_sec_xbrl_response(result), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.19.0 — Weather/environmental)
    # ---------------------------------------------------------------------
    if source == "noaa":
        result = noaa.search_noaa(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return noaa.parse_noaa_response(result), {}
    if source == "openweather":
        result = openweather.search_openweather(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return openweather.parse_openweather_response(result), {}
    if source == "epa_airnow":
        result = epa_airnow.search_epa_airnow(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return epa_airnow.parse_epa_airnow_response(result), {}
    if source == "nasa_power":
        result = nasa_power.search_nasa_power(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return nasa_power.parse_nasa_power_response(result), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.20.0 — News aggregation)
    # ---------------------------------------------------------------------
    if source == "google_news":
        result = google_news.search_google_news(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return google_news.parse_google_news_response(result, depth=depth), {}
    if source == "newsapi":
        result = newsapi.search_newsapi(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return newsapi.parse_newsapi_response(result), {}
    if source == "gdelt":
        result = gdelt.search_gdelt(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return gdelt.parse_gdelt_response(result), {}
    if source == "mediacloud":
        result = mediacloud.search_mediacloud(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return mediacloud.parse_mediacloud_response(result), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.21.0 — Developer signals)
    # ---------------------------------------------------------------------
    if source == "npm_registry":
        result = npm_registry.search_npm_registry(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return npm_registry.parse_npm_registry_response(result), {}
    if source == "pypi":
        result = pypi.search_pypi(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return pypi.parse_pypi_response(result), {}
    if source == "homebrew":
        result = homebrew.search_homebrew(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return homebrew.parse_homebrew_response(result, topic=subquery.search_query, depth=depth), {}
    if source == "docker_hub":
        result = docker_hub.search_docker_hub(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return docker_hub.parse_docker_hub_response(result), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.22.0 — Crypto/on-chain)
    # ---------------------------------------------------------------------
    if source == "coingecko":
        result = coingecko.search_coingecko(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return coingecko.parse_coingecko_response(result), {}
    if source == "defillama":
        result = defillama.search_defillama(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return defillama.parse_defillama_response(result, topic=subquery.search_query, depth=depth), {}
    if source == "etherscan":
        result = etherscan.search_etherscan(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return etherscan.parse_etherscan_response(result), {}
    if source == "dune":
        result = dune.search_dune(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return dune.parse_dune_response(result), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.23.0 — Federated social)
    # ---------------------------------------------------------------------
    if source == "mastodon":
        result = mastodon.search_mastodon(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return mastodon.parse_mastodon_response(result), {}
    if source == "lemmy":
        result = lemmy.search_lemmy(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return lemmy.parse_lemmy_response(result), {}
    if source == "farcaster":
        result = farcaster.search_farcaster(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return farcaster.parse_farcaster_response(result), {}
    if source == "discord":
        result = discord_source.search_discord(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return discord_source.parse_discord_response(result), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.24.0 — Geographic/Events/Gov stats)
    # ---------------------------------------------------------------------
    if source == "cdc_data":
        result = cdc_data.search_cdc_data(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return cdc_data.parse_cdc_data_response(result), {}
    if source == "usda_ers":
        result = usda_ers.search_usda_ers(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return usda_ers.parse_usda_ers_response(result), {}
    if source == "google_places":
        result = google_places.search_google_places(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return google_places.parse_google_places_response(result), {}
    if source == "foursquare":
        result = foursquare.search_foursquare(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return foursquare.parse_foursquare_response(result), {}
    if source == "eventbrite":
        result = eventbrite.search_eventbrite(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return eventbrite.parse_eventbrite_response(result), {}
    if source == "meetup":
        result = meetup.search_meetup(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return meetup.parse_meetup_response(result), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.25.0 — Market/creator/podcast envelopes)
    # ---------------------------------------------------------------------
    if source == "crunchbase":
        result = crunchbase.search_crunchbase(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return crunchbase.parse_crunchbase_response(result), {}
    if source == "similarweb":
        result = similarweb.search_similarweb(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return similarweb.parse_similarweb_response(result), {}
    if source == "builtwith":
        result = builtwith.search_builtwith(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return builtwith.parse_builtwith_response(result), {}
    if source == "buzzsumo":
        result = buzzsumo.search_buzzsumo(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return buzzsumo.parse_buzzsumo_response(result), {}
    if source == "listen_notes":
        result = listen_notes.search_listen_notes(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return listen_notes.parse_listen_notes_response(result), {}
    if source == "podchaser":
        result = podchaser.search_podchaser(subquery.search_query, from_date, to_date, depth=depth, config=config)
        return podchaser.parse_podchaser_response(result), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.27.0 — Latent demand signals)
    # ---------------------------------------------------------------------
    if source == "cpsc_saferproducts":
        result = cpsc_saferproducts.search_cpsc_saferproducts(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return cpsc_saferproducts.parse_cpsc_saferproducts_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "instacart_trends":
        result = instacart_trends.search_instacart_trends(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return instacart_trends.parse_instacart_trends_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "amazon_brand_analytics":
        result = amazon_brand_analytics.search_amazon_brand_analytics(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return amazon_brand_analytics.parse_amazon_brand_analytics_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "shopify_analytics":
        result = shopify_analytics.search_shopify_analytics(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return shopify_analytics.parse_shopify_analytics_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    # ---------------------------------------------------------------------
    # Signalsweep-unique source dispatch (v3.28.0 — Dark demand signals)
    # ---------------------------------------------------------------------
    if source == "cfpb_complaints":
        result = cfpb_complaints.search_cfpb_complaints(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return cfpb_complaints.parse_cfpb_complaints_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "indiegogo":
        result = indiegogo.search_indiegogo(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return indiegogo.parse_indiegogo_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "common_crawl":
        result = common_crawl.search_common_crawl(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return common_crawl.parse_common_crawl_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "google_patents":
        result = google_patents.search_google_patents(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return google_patents.parse_google_patents_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "nutritionix":
        result = nutritionix.search_nutritionix(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return nutritionix.parse_nutritionix_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "powerreviews":
        result = powerreviews.search_powerreviews(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return powerreviews.parse_powerreviews_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "spotify_podcasts":
        result = spotify_podcasts.search_spotify_podcasts(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return spotify_podcasts.parse_spotify_podcasts_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "stamped_reviews":
        result = stamped_reviews.search_stamped_reviews(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return stamped_reviews.parse_stamped_reviews_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "aftership_returns":
        result = aftership_returns.search_aftership_returns(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return aftership_returns.parse_aftership_returns_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "gorgias_tickets":
        result = gorgias_tickets.search_gorgias_tickets(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return gorgias_tickets.parse_gorgias_tickets_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "klaviyo_events":
        result = klaviyo_events.search_klaviyo_events(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return klaviyo_events.parse_klaviyo_events_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "nhtsa_complaints":
        result = nhtsa_complaints.search_nhtsa_complaints(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return nhtsa_complaints.parse_nhtsa_complaints_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "kickstarter":
        result = kickstarter.search_kickstarter(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return kickstarter.parse_kickstarter_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "loop_returns":
        result = loop_returns.search_loop_returns(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return loop_returns.parse_loop_returns_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "yotpo_reviews":
        result = yotpo_reviews.search_yotpo_reviews(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return yotpo_reviews.parse_yotpo_reviews_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "open_food_facts":
        result = open_food_facts.search_open_food_facts(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return open_food_facts.parse_open_food_facts_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    if source == "usda_fooddata":
        result = usda_fooddata.search_usda_fooddata(
            subquery.search_query, from_date, to_date, depth=depth, config=config,
        )
        return usda_fooddata.parse_usda_fooddata_response(
            result, query=subquery.search_query, from_date=from_date, to_date=to_date, depth=depth,
        ), {}
    raise RuntimeError(f"Unsupported source: {source}")


def _google_key(config: dict[str, Any]) -> str | None:
    return config.get("GOOGLE_API_KEY") or config.get("GEMINI_API_KEY") or config.get("GOOGLE_GENAI_API_KEY")




def _mock_stream_results(source: str, subquery: schema.SubQuery) -> tuple[list[dict], dict]:
    payloads = {
        "reddit": [
            {
                "id": "R1",
                "title": f"{subquery.search_query} discussion thread",
                "url": "https://reddit.com/r/example/comments/1",
                "subreddit": "example",
                "date": dates.get_date_range(5)[0],
                "engagement": {"score": 120, "num_comments": 48, "upvote_ratio": 0.91},
                "selftext": f"Community discussion about {subquery.search_query}.",
                "top_comments": [{"excerpt": "Strong firsthand feedback from users."}],
                "relevance": 0.82,
                "why_relevant": "Mock Reddit result",
            }
        ],
        "x": [
            {
                "id": "X1",
                "text": f"People on X are discussing {subquery.search_query} right now.",
                "url": "https://x.com/example/status/1",
                "author_handle": "example",
                "date": dates.get_date_range(2)[0],
                "engagement": {"likes": 200, "reposts": 35, "replies": 18, "quotes": 4},
                "relevance": 0.79,
                "why_relevant": "Mock X result",
            }
        ],
        "digg": [
            {
                "id": "mock-digg-1",
                "title": f"Digg cluster about {subquery.search_query}",
                "tldr": f"Digg's cluster summary says people are actively discussing {subquery.search_query}.",
                "url": "https://di.gg/ai/mock-digg-1",
                "date": dates.get_date_range(3)[0],
                "engagement": {"postCount": 12, "uniqueAuthors": 9, "rank_score": 80},
                "relevance": 0.8,
                "why_relevant": "Mock Digg cluster",
                "posts": [
                    {
                        "text": f"Representative X post about {subquery.search_query}",
                        "author": "example",
                        "url": "https://x.com/example/status/2",
                    }
                ],
            }
        ],
        "grounding": [
            {
                "id": "WB1",
                "title": f"{subquery.search_query} article",
                "url": "https://example.com/article",
                "source_domain": "example.com",
                "snippet": f"Recent web reporting about {subquery.search_query}.",
                "date": dates.get_date_range(7)[0],
                "relevance": 0.88,
                "why_relevant": "Brave web search",
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.5)
        "linkedin": [
            {
                "id": "LI1",
                "text": f"LinkedIn perspective on {subquery.search_query} — worth reading.",
                "url": "https://linkedin.com/posts/example",
                "author_name": "Example Executive",
                "author_headline": "VP at Example Corp",
                "date": dates.get_date_range(6)[0],
                "engagement": {"likes": 85, "comments": 12, "reposts": 7},
                "relevance": 0.76,
                "why_relevant": "Mock LinkedIn post",
            }
        ],
        "stackoverflow": [
            {
                "question_id": "SO1",
                "title": f"How do I {subquery.search_query}?",
                "body_snippet": f"I am trying to understand {subquery.search_query}...",
                "url": "https://stackoverflow.com/q/1",
                "author": "exampleuser",
                "date": dates.get_date_range(10)[0],
                "engagement": {"score": 15, "answer_count": 3, "view_count": 1200},
                "tags": ["example", "question"],
                "is_answered": True,
                "relevance": 0.72,
                "why_relevant": "Mock Stack Overflow question",
            }
        ],
        "rss_blogs": [
            {
                "id": "BLOG1",
                "title": f"Deep dive on {subquery.search_query}",
                "description": f"Substack essay exploring {subquery.search_query} in depth.",
                "url": "https://example.substack.com/p/deep-dive",
                "author": "Example Writer",
                "date": dates.get_date_range(4)[0],
                "platform": "substack",
                "categories": ["analysis"],
                "relevance": 0.74,
                "why_relevant": "Mock Substack article",
            }
        ],
        "podcasts": [
            {
                "episode_id": "POD1",
                "title": f"Conversation about {subquery.search_query}",
                "description": f"Long-form podcast discussion of {subquery.search_query}.",
                "podcast_name": "Example Podcast",
                "audio_url": "https://example.com/ep1.mp3",
                "duration": "00:45:30",
                "date": dates.get_date_range(8)[0],
                "engagement": {"popularity_rank": 42},
                "relevance": 0.71,
                "why_relevant": "Mock podcast episode",
            }
        ],
        "producthunt": [
            {
                "id": "PH1",
                "name": "Example Product",
                "tagline": f"A new approach to {subquery.search_query}",
                "description": f"Product solving {subquery.search_query} problems.",
                "url": "https://producthunt.com/products/example",
                "maker": "example-maker",
                "website": "https://example.com",
                "topics": ["developer-tools"],
                "date": dates.get_date_range(3)[0],
                "engagement": {"votes": 120, "comments": 15, "reviews": 4},
                "relevance": 0.73,
                "why_relevant": "Mock Product Hunt launch",
            }
        ],
        "x_sc": [
            {
                "id": "XSC1",
                "text": f"[via ScrapeCreators] Observations on {subquery.search_query}.",
                "url": "https://x.com/example_sc/status/1",
                "author_handle": "example_sc",
                "date": dates.get_date_range(1)[0],
                "engagement": {"likes": 150, "reposts": 22, "replies": 8, "quotes": 3},
                "relevance": 0.77,
                "why_relevant": "Mock ScrapeCreators X post",
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.6 — Free/Public Data)
        "sec_edgar": [
            {
                "item_id": "0001234567-26-000001",
                "source": "sec_edgar",
                "title": f"Example Corp — 10-K (topic: {subquery.search_query})",
                "body": f"Example Corp filed 10-K discussing {subquery.search_query}. CIK: 0001234567.",
                "url": "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001/0001234567-26-000001-index.htm",
                "author": "Example Corp",
                "container": "10-K",
                "published_at": dates.get_date_range(5)[0],
                "engagement": {},
                "relevance_hint": 0.7,
                "why_relevant": "Mock SEC EDGAR filing",
                "metadata": {"form": "10-K", "cik": "0001234567", "accession_number": "0001234567-26-000001", "company_name": "Example Corp", "file_type": "10-K"},
            }
        ],
        "arxiv": [
            {
                "id": "2604.00001v1",
                "title": f"Advances in {subquery.search_query}",
                "snippet": f"We present new theoretical results on {subquery.search_query}.",
                "url": "https://arxiv.org/abs/2604.00001v1",
                "date": dates.get_date_range(8)[0],
                "source_domain": "arxiv.org",
                "relevance": 0.75,
                "why_relevant": "Mock arXiv preprint",
                "metadata": {"arxiv_id": "2604.00001v1", "primary_category": "cs.AI", "first_author": "Example Author"},
            }
        ],
        "biorxiv": [
            {
                "id": "10.1101/2026.04.01.123456",
                "title": f"Biological study of {subquery.search_query}",
                "snippet": f"Biorxiv preprint investigating {subquery.search_query}.",
                "url": "https://www.biorxiv.org/content/10.1101/2026.04.01.123456v1",
                "date": dates.get_date_range(6)[0],
                "source_domain": "biorxiv.org",
                "relevance": 0.72,
                "why_relevant": "Mock bioRxiv preprint",
                "metadata": {"doi": "10.1101/2026.04.01.123456", "category": "molecular biology", "first_author": "Example Researcher", "server": "biorxiv"},
            }
        ],
        "medrxiv": [
            {
                "id": "10.1101/2026.04.02.987654",
                "title": f"Clinical study of {subquery.search_query}",
                "snippet": f"Medrxiv preprint on {subquery.search_query} outcomes.",
                "url": "https://www.medrxiv.org/content/10.1101/2026.04.02.987654v1",
                "date": dates.get_date_range(7)[0],
                "source_domain": "medrxiv.org",
                "relevance": 0.72,
                "why_relevant": "Mock medRxiv preprint",
                "metadata": {"doi": "10.1101/2026.04.02.987654", "category": "epidemiology", "first_author": "Example Clinician", "server": "medrxiv"},
            }
        ],
        "semantic_scholar": [
            {
                "id": "s2paper1",
                "title": f"Scholarly review of {subquery.search_query}",
                "snippet": f"Comprehensive survey of {subquery.search_query}.",
                "url": "https://www.semanticscholar.org/paper/s2paper1",
                "date": dates.get_date_range(10)[0],
                "source_domain": "semanticscholar.org",
                "relevance": 0.73,
                "why_relevant": "Mock Semantic Scholar paper",
                "engagement": {"citation_count": 25},
                "metadata": {"paper_id": "s2paper1", "venue": "NeurIPS", "citation_count": 25, "first_author": "Example Scholar"},
            }
        ],
        "openalex": [
            {
                "id": "https://openalex.org/W1",
                "title": f"OpenAlex work on {subquery.search_query}",
                "snippet": f"Research article on {subquery.search_query}.",
                "url": "https://doi.org/10.5678/example",
                "date": dates.get_date_range(9)[0],
                "source_domain": "openalex.org",
                "relevance": 0.72,
                "why_relevant": "Mock OpenAlex work",
                "engagement": {"citation_count": 18},
                "metadata": {"openalex_id": "https://openalex.org/W1", "doi": "10.5678/example", "venue": "ICML", "citation_count": 18, "is_oa": True},
            }
        ],
        "pubmed": [
            {
                "id": "40000001",
                "title": f"PubMed study on {subquery.search_query}",
                "snippet": f"Clinical study of {subquery.search_query}.",
                "url": "https://pubmed.ncbi.nlm.nih.gov/40000001/",
                "date": dates.get_date_range(12)[0],
                "source_domain": "pubmed.ncbi.nlm.nih.gov",
                "relevance": 0.73,
                "why_relevant": "Mock PubMed article",
                "metadata": {"pmid": "40000001", "doi": "10.1000/example", "journal": "Example Journal", "first_author": "Smith J"},
            }
        ],
        "datagov": [
            {
                "id": "example-dataset",
                "title": f"US dataset on {subquery.search_query}",
                "snippet": f"Federal dataset with {subquery.search_query} data.",
                "url": "https://catalog.data.gov/dataset/example-dataset",
                "date": dates.get_date_range(30)[0],
                "source_domain": "catalog.data.gov",
                "relevance": 0.6,
                "why_relevant": "Mock data.gov dataset",
                "metadata": {"organization": "Example Agency", "tags": ["example"], "num_resources": 3},
            }
        ],
        "bls": [
            {
                "id": "EXAMPLE001",
                "title": f"BLS series related to {subquery.search_query}",
                "snippet": "Mock BLS time series.",
                "url": "https://data.bls.gov/timeseries/EXAMPLE001",
                "date": dates.get_date_range(14)[0],
                "source_domain": "bls.gov",
                "relevance": 0.65,
                "why_relevant": "Mock BLS series",
                "metadata": {"series_id": "EXAMPLE001", "tags": [subquery.search_query.lower()]},
            }
        ],
        "worldbank": [
            {
                "id": "EXAMPLE.INDICATOR",
                "title": f"World Bank indicator: {subquery.search_query}",
                "snippet": f"Global indicator measuring {subquery.search_query}.",
                "url": "https://data.worldbank.org/indicator/EXAMPLE.INDICATOR",
                "date": dates.get_date_range(20)[0],
                "source_domain": "worldbank.org",
                "relevance": 0.6,
                "why_relevant": "Mock WorldBank indicator",
                "metadata": {"indicator_id": "EXAMPLE.INDICATOR", "source_organization": "World Bank"},
            }
        ],
        "eurostat": [
            {
                "id": "example_ds",
                "title": f"Eurostat dataset: {subquery.search_query}",
                "snippet": "Mock Eurostat dataset.",
                "url": "https://ec.europa.eu/eurostat/databrowser/view/example_ds/default/table",
                "date": dates.get_date_range(25)[0],
                "source_domain": "eurostat.ec.europa.eu",
                "relevance": 0.6,
                "why_relevant": "Mock Eurostat dataset",
                "metadata": {"dataset_code": "example_ds", "tags": [subquery.search_query.lower()]},
            }
        ],
        "wiki_pageviews": [
            {
                "item_id": f"wiki_pv:{subquery.search_query}",
                "source": "wiki_pageviews",
                "title": f"Wikipedia pageviews: {subquery.search_query}",
                "body": f"Wikipedia pageviews for '{subquery.search_query}': 12,000 total views, 400 average daily, peak on {dates.get_date_range(3)[0]} with 800 views.",
                "url": f"https://en.wikipedia.org/wiki/{subquery.search_query.replace(' ', '_')}",
                "author": None,
                "container": "en.wikipedia.org",
                "published_at": dates.get_date_range(1)[0],
                "engagement": {"total_views": 12000, "avg_daily": 400},
                "relevance_hint": 0.7,
                "why_relevant": f"Interest signal for '{subquery.search_query}' via Wikipedia pageviews",
                "metadata": {
                    "article_title": subquery.search_query,
                    "daily_series": [],
                    "avg_daily_views": 400,
                    "peak_date": dates.get_date_range(3)[0],
                    "peak_views": 800,
                    "total_views": 12000,
                    "data_points": 30,
                },
            }
        ],
        "wiki_recent_changes": [
            {
                "id": "rc:12345:2026-04-10T12:00:00Z",
                "title": f"Edit to {subquery.search_query}",
                "snippet": f"Wikipedia edit updating content about {subquery.search_query}.",
                "url": f"https://en.wikipedia.org/wiki/{subquery.search_query.replace(' ', '_')}",
                "date": dates.get_date_range(1)[0],
                "source_domain": "en.wikipedia.org",
                "relevance": 0.5,
                "why_relevant": f"Wikipedia edit on '{subquery.search_query}'",
                "metadata": {"article_title": subquery.search_query, "editor": "ExampleEditor", "size_delta": 250, "comment": "Updated content"},
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.6.1 — public-data backlog)
        "uk_ons": [
            {
                "id": "cpih01",
                "title": f"UK ONS dataset on {subquery.search_query}",
                "snippet": f"Mock UK Office for National Statistics dataset covering {subquery.search_query}.",
                "url": "https://www.ons.gov.uk/datasets/cpih01",
                "date": dates.get_date_range(15)[0],
                "source_domain": "ons.gov.uk",
                "relevance": 0.6,
                "why_relevant": "Mock UK ONS dataset",
                "metadata": {"release_date": dates.get_date_range(15)[0], "type": "dataset"},
            }
        ],
        "imf": [
            {
                "id": "EXAMPLEDF",
                "title": f"IMF dataflow: {subquery.search_query}",
                "snippet": "Mock IMF SDMX dataflow.",
                "url": "https://data.imf.org/regular.aspx?key=EXAMPLEDF",
                "date": dates.get_date_range(20)[0],
                "source_domain": "imf.org",
                "relevance": 0.6,
                "why_relevant": "Mock IMF dataset",
                "metadata": {"dataflow_id": "EXAMPLEDF", "agency": "IMF"},
            }
        ],
        "crossref": [
            {
                "id": "10.1038/s41586-2026-EXAMPLE",
                "title": f"Research paper on {subquery.search_query}",
                "snippet": "Mock CrossRef-indexed scholarly work abstract.",
                "url": "https://doi.org/10.1038/s41586-2026-EXAMPLE",
                "date": dates.get_date_range(20)[0],
                "source_domain": "crossref.org",
                "author": "Doe, Alice et al.",
                "relevance": 0.7,
                "why_relevant": "Mock CrossRef journal-article in Nature",
                "metadata": {
                    "doi": "10.1038/s41586-2026-EXAMPLE",
                    "container": "Nature",
                    "publisher": "Nature Publishing Group",
                    "type": "journal-article",
                    "subjects": ["Multidisciplinary"],
                },
            }
        ],
        "orcid": [
            {
                "id": "0000-0001-2345-6789",
                "title": "Alice Researcher",
                "snippet": "Stanford University; MIT",
                "url": "https://orcid.org/0000-0001-2345-6789",
                "date": None,
                "source_domain": "orcid.org",
                "author": "Alice Researcher",
                "relevance": 0.55,
                "why_relevant": "Mock ORCID researcher record",
                "metadata": {
                    "orcid_id": "0000-0001-2345-6789",
                    "institutions": ["Stanford University", "MIT"],
                    "other_names": [],
                    "email_count": 0,
                },
            }
        ],
        "bea": [
            {
                "id": "Regional",
                "title": "Regional GDP and personal income",
                "snippet": "Mock BEA dataset (regional accounts).",
                "url": "https://apps.bea.gov/iTable/?reqid=Regional",
                "date": dates.get_date_range(30)[0],
                "source_domain": "bea.gov",
                "relevance": 0.6,
                "why_relevant": "Mock BEA dataset",
                "metadata": {"dataset_name": "Regional"},
            }
        ],
        "usda_nass": [
            {
                "id": "CORN:PRODUCTION:2024:IOWA",
                "title": f"USDA NASS — {subquery.search_query} production (2024)",
                "snippet": "15,148,038,000 BU — IOWA",
                "url": "https://quickstats.nass.usda.gov/results",
                "date": dates.get_date_range(20)[0],
                "source_domain": "nass.usda.gov",
                "relevance": 0.6,
                "why_relevant": "Mock USDA NASS production record",
                "metadata": {
                    "commodity": subquery.search_query.upper(),
                    "statistic": "PRODUCTION",
                    "unit": "BU",
                    "value": "15,148,038,000",
                    "year": "2024",
                    "location": "IOWA",
                },
            }
        ],
        "wikidata": [
            {
                "id": "Q312",
                "title": f"Wikidata entity for {subquery.search_query}",
                "snippet": "Mock Wikidata entity description",
                "url": "https://www.wikidata.org/wiki/Q312",
                "date": dates.get_date_range(1)[0],
                "source_domain": "wikidata.org",
                "relevance": 0.7,
                "why_relevant": f"Mock Wikidata entity: {subquery.search_query}",
                "metadata": {"qid": "Q312", "match_type": "label", "match_text": subquery.search_query},
            }
        ],
        "pubmed_efetch": [
            {
                "id": "12345678",
                "title": f"Full-abstract PubMed paper on {subquery.search_query}",
                "snippet": f"BACKGROUND: We investigated {subquery.search_query}. METHODS: ... RESULTS: ... CONCLUSIONS: ...",
                "content": f"BACKGROUND: We investigated {subquery.search_query}. METHODS: ... RESULTS: ... CONCLUSIONS: ...",
                "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
                "date": dates.get_date_range(15)[0],
                "source_domain": "pubmed.ncbi.nlm.nih.gov",
                "author": "Doe, Alice",
                "relevance": 0.75,
                "why_relevant": "Mock PubMed full abstract in Nature Medicine",
                "metadata": {
                    "pmid": "12345678",
                    "journal": "Nature Medicine",
                    "first_author": "Doe, Alice",
                    "all_authors": ["Doe, Alice", "Lee, Bob"],
                    "abstract_sections": 4,
                },
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.7 — Amazon/ecommerce intelligence)
        "keepa": [
            {
                "id": "B08MOCKASIN",
                "title": f"Example Amazon product for '{subquery.search_query}'",
                "snippet": "Brand: ExampleBrand · BSR: #1,200 · Price: $29.99 · Category: Example Category",
                "url": "https://www.amazon.com/dp/B08MOCKASIN",
                "source_domain": "amazon.com",
                "date": None,
                "relevance": 0.78,
                "why_relevant": f"Amazon product match for '{subquery.search_query}'",
                "metadata": {
                    "asin": "B08MOCKASIN",
                    "brand": "ExampleBrand",
                    "current_bsr": 1200,
                    "current_price_cents": 2999,
                    "primary_category": "Example Category",
                    "domain_id": "1",
                },
            }
        ],
        "helium10": [
            {
                "id": "B08H10MOCK",
                "title": f"Helium10 mock product for '{subquery.search_query}'",
                "snippet": "Brand: MockBrand · BSR: #1,800 · Monthly revenue: $245,000 · Monthly sales: 4,100",
                "url": "https://www.amazon.com/dp/B08H10MOCK",
                "source_domain": "amazon.com",
                "relevance": 0.75,
                "why_relevant": f"Helium10 product match for '{subquery.search_query}'",
                "metadata": {"asin": "B08H10MOCK", "brand": "MockBrand", "bsr": 1800, "monthly_revenue": 245000, "monthly_sales": 4100},
            }
        ],
        "junglescout": [
            {
                "id": "B08JSMOCK",
                "title": f"Jungle Scout mock product for '{subquery.search_query}'",
                "snippet": "Brand: JSMock · Category: Mock Category · BSR: #2,100 · Est. sales/mo: 3,500",
                "url": "https://www.amazon.com/dp/B08JSMOCK",
                "source_domain": "amazon.com",
                "relevance": 0.73,
                "why_relevant": f"Jungle Scout product match for '{subquery.search_query}'",
                "metadata": {"asin": "B08JSMOCK", "brand": "JSMock", "category": "Mock Category", "rank": 2100, "estimated_sales": 3500},
            }
        ],
        "datadive": [
            {
                "id": f"datadive:{subquery.search_query}",
                "title": f"Amazon keyword: {subquery.search_query}",
                "snippet": "Searches/mo: 145,000 · Competition: 0.72 · CPC: $1.35",
                "url": f"https://www.amazon.com/s?k={subquery.search_query.replace(' ', '+')}",
                "source_domain": "amazon.com",
                "relevance": 0.72,
                "why_relevant": f"DataDive keyword intel for '{subquery.search_query}'",
                "metadata": {"keyword": subquery.search_query, "search_volume": 145000, "competition": 0.72, "cpc": 1.35, "top_asins": ["B08MOCK1", "B08MOCK2"]},
            }
        ],
        "smartscout": [
            {
                "id": "smartscout:MockBrand",
                "title": "Amazon brand: MockBrand",
                "snippet": "Category: Mock Category · Monthly revenue: $185,000 · Market share: 8.0% · ASINs: 12",
                "url": "https://www.amazon.com/s?k=MockBrand",
                "source_domain": "amazon.com",
                "relevance": 0.70,
                "why_relevant": f"SmartScout brand intel for '{subquery.search_query}'",
                "metadata": {"brand": "MockBrand", "monthly_revenue": 185000, "market_share": 0.08, "num_asins": 12, "primary_category": "Mock Category"},
            }
        ],
        "amazon_reviews": [
            {
                "id": "ARmock1",
                "title": "Best product I've bought in months",
                "snippet": f"Mock Amazon review praising {subquery.search_query}. Solid feel, great value.",
                "url": "https://www.amazon.com/dp/B08MOCKREV",
                "source_domain": "amazon.com",
                "date": dates.get_date_range(7)[0],
                "relevance": 0.72,
                "why_relevant": "Amazon review (5★)",
                "metadata": {"asin": "B08MOCKREV", "author": "MockCustomer", "rating": 5, "verified_purchase": True, "helpful_count": 24},
            }
        ],
        "tiktok_shop": [
            {
                "id": "TTSmock1",
                "title": f"Mock TikTok Shop product for '{subquery.search_query}'",
                "snippet": "Seller: MockShop · USD 45.99 · Sold: 12,500 · 4.7★",
                "url": "https://www.tiktok.com/shop/product/TTSmock1",
                "source_domain": "tiktok.com",
                "date": dates.get_date_range(4)[0],
                "relevance": 0.68,
                "why_relevant": f"TikTok Shop listing for '{subquery.search_query}'",
                "metadata": {"seller": "MockShop", "price": 45.99, "currency": "USD", "sold_count": 12500, "rating": 4.7},
            }
        ],
        "sp_api": [
            {
                "id": "B08MOCKSP",
                "title": f"SP-API mock catalog item for '{subquery.search_query}'",
                "snippet": "Brand: MockBrand · Type: EXAMPLE_TYPE",
                "url": "https://www.amazon.com/dp/B08MOCKSP",
                "source_domain": "amazon.com",
                "relevance": 0.76,
                "why_relevant": f"SP-API catalog match for '{subquery.search_query}'",
                "metadata": {"asin": "B08MOCKSP", "brand": "MockBrand", "manufacturer": "MockBrand", "product_type": "EXAMPLE_TYPE", "upc": "012345678905"},
            }
        ],
        # v3.8 — Deep Research LLM providers (mock fixtures)
        "chatgpt_deep_research": [
            {
                "id": "CGPT_DR1_MOCK",
                "title": f"ChatGPT Deep Research: {subquery.search_query}",
                "snippet": f"Mock ChatGPT Deep Research synthesis for '{subquery.search_query}' (~5K words). Three citations.",
                "url": "",
                "source_domain": "openai.com",
                "date": None,
                "relevance": 0.92,
                "why_relevant": f"ChatGPT Deep Research synthesis for '{subquery.search_query}'",
                "metadata": {
                    "provider": "chatgpt_deep_research",
                    "model": "o3-deep-research",
                    "route": "direct",
                    "synthesis": f"Mock synthesis body for '{subquery.search_query}' " * 50,
                    "synthesis_length": 5000,
                    "citation_count": 3,
                    "estimated_cost_usd": 5.00,
                },
            }
        ],
        "claude_research": [
            {
                "id": "CLAUDE_R1_MOCK",
                "title": f"Claude Research: {subquery.search_query}",
                "snippet": f"Mock Claude Research synthesis with extended thinking for '{subquery.search_query}'.",
                "url": "",
                "source_domain": "anthropic.com",
                "date": None,
                "relevance": 0.92,
                "why_relevant": f"Claude Research synthesis for '{subquery.search_query}'",
                "metadata": {
                    "provider": "claude_research",
                    "model": "claude-opus-4-6",
                    "route": "direct",
                    "synthesis": f"Mock Claude synthesis for '{subquery.search_query}' " * 50,
                    "synthesis_length": 5000,
                    "citation_count": 4,
                    "estimated_cost_usd": 3.00,
                },
            }
        ],
        "gemini_deep_research": [
            {
                "id": "GEM_DR1_MOCK",
                "title": f"Gemini Deep Research: {subquery.search_query}",
                "snippet": f"Mock Gemini Deep Research synthesis with googleSearch grounding for '{subquery.search_query}'.",
                "url": "",
                "source_domain": "google.com",
                "date": None,
                "relevance": 0.92,
                "why_relevant": f"Gemini Deep Research synthesis for '{subquery.search_query}'",
                "metadata": {
                    "provider": "gemini_deep_research",
                    "model": "gemini-2.5-pro",
                    "route": "direct",
                    "synthesis": f"Mock Gemini synthesis for '{subquery.search_query}' " * 40,
                    "synthesis_length": 4000,
                    "citation_count": 3,
                    "estimated_cost_usd": 2.00,
                },
            }
        ],
        "grok_deepsearch": [
            {
                "id": "GROK_DS1_MOCK",
                "title": f"Grok DeepSearch: {subquery.search_query}",
                "snippet": f"Mock Grok DeepSearch synthesis (real-time + X-native) for '{subquery.search_query}'.",
                "url": "",
                "source_domain": "x.ai",
                "date": None,
                "relevance": 0.92,
                "why_relevant": f"Grok DeepSearch synthesis for '{subquery.search_query}'",
                "metadata": {
                    "provider": "grok_deepsearch",
                    "model": "grok-4",
                    "route": "direct",
                    "synthesis": f"Mock Grok synthesis with X-native signals for '{subquery.search_query}' " * 30,
                    "synthesis_length": 3500,
                    "citation_count": 4,
                    "estimated_cost_usd": 1.00,
                    "strengths": "real-time + X-native signals",
                },
            }
        ],
        "openrouter_research": [
            {
                "id": "OR_R1_MOCK",
                "title": f"OpenRouter Research (perplexity/sonar-deep-research): {subquery.search_query}",
                "snippet": f"Mock OpenRouter routed deep-research synthesis for '{subquery.search_query}'.",
                "url": "",
                "source_domain": "openrouter.ai",
                "date": None,
                "relevance": 0.90,
                "why_relevant": f"OpenRouter (perplexity/sonar-deep-research) deep-research synthesis for '{subquery.search_query}'",
                "metadata": {
                    "provider": "openrouter_research",
                    "model": "perplexity/sonar-deep-research",
                    "route": "openrouter",
                    "synthesis": f"Mock OpenRouter synthesis for '{subquery.search_query}' " * 30,
                    "synthesis_length": 3000,
                    "citation_count": 3,
                    "estimated_cost_usd": 1.00,
                },
            }
        ],
        "ads_api": [
            {
                "id": "999999999999999",
                "title": f"SP campaign: Mock - {subquery.search_query} - Exact",
                "snippet": "State: enabled · Daily budget: $50.00 · Targeting: manual",
                "url": "https://advertising.amazon.com/cm/sp/campaigns/999999999999999",
                "source_domain": "advertising.amazon.com",
                "date": "20260201",
                "relevance": 0.80,
                "why_relevant": f"Ads API campaign match for '{subquery.search_query}'",
                "metadata": {
                    "campaign_id": 999999999999999,
                    "name": f"Mock - {subquery.search_query} - Exact",
                    "state": "enabled",
                    "daily_budget": 50.00,
                    "targeting_type": "manual",
                    "start_date": "20260201",
                    "end_date": None,
                },
            }
        ],
        "google_shopping": [
            {
                "id": "GSmock1",
                "title": f"Shopping result for '{subquery.search_query}' on Amazon",
                "snippet": "Merchant: Amazon · Mock shopping result preview text.",
                "url": "https://www.amazon.com/dp/B08MOCKGS",
                "source_domain": "amazon.com",
                "date": dates.get_date_range(5)[0],
                "relevance": 0.70,
                "why_relevant": f"Shopping-domain result for '{subquery.search_query}'",
                "metadata": {"merchant": "Amazon", "exa_score": 0.87, "author": None},
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.9 — Demand signals)
        "google_trends": [
            {
                "id": f"google_trends:{subquery.search_query}:US",
                "title": f"Google Trends: {subquery.search_query}",
                "snippet": f"Google Trends interest for '{subquery.search_query}' (US): peak 100 on {dates.get_date_range(3)[0]}, avg 62.0 across 12 points.",
                "url": f"https://trends.google.com/trends/explore?q={subquery.search_query}&geo=US",
                "source_domain": "trends.google.com",
                "date": dates.get_date_range(3)[0],
                "relevance": 0.7,
                "why_relevant": f"Search-interest trajectory for '{subquery.search_query}'",
                "engagement_score": 100.0,
                "metadata": {
                    "topic": subquery.search_query,
                    "geo": "US",
                    "peak_value": 100,
                    "peak_date": dates.get_date_range(3)[0],
                    "avg_value": 62.0,
                    "data_points": 12,
                },
            }
        ],
        "pinterest_trends": [
            {
                "id": f"pinterest_trend:{subquery.search_query}",
                "title": f"{subquery.search_query} decor ideas",
                "snippet": "Trending Pinterest search (+143%)",
                "url": f"https://pinterest.com/search/pins/?q={subquery.search_query}",
                "source_domain": "pinterest.com",
                "date": dates.get_date_range(3)[0],
                "relevance": 0.65,
                "why_relevant": f"Pinterest trending: {subquery.search_query} decor",
                "engagement_score": 143.0,
                "metadata": {"growth_pct": 143.0, "region": "US"},
            }
        ],
        "tiktok_creative_center": [
            {
                "id": f"tiktok_cc:#{subquery.search_query}",
                "title": f"#{subquery.search_query}",
                "snippet": f"TikTok trending hashtag — 5000 posts, 2500000 views",
                "url": f"https://www.tiktok.com/tag/{subquery.search_query}",
                "source_domain": "tiktok.com",
                "date": dates.get_date_range(2)[0],
                "relevance": 0.65,
                "why_relevant": f"TikTok Creative Center trending: #{subquery.search_query}",
                "engagement_score": 2500000.0,
                "metadata": {"posts": 5000, "views": 2500000, "region": "US"},
            }
        ],
        "amazon_autocomplete": [
            {
                "id": f"amazon_auto:US:{subquery.search_query}",
                "title": f"{subquery.search_query} accessories",
                "snippet": "Amazon United States autocomplete suggestion",
                "url": f"https://www.amazon.com/s?k={subquery.search_query}+accessories",
                "source_domain": "amazon.com",
                "date": dates.get_date_range(1)[0],
                "relevance": 0.65,
                "why_relevant": f"Amazon US buyer query: {subquery.search_query} accessories",
                "metadata": {
                    "marketplace": "US",
                    "country_name": "United States",
                    "query": subquery.search_query,
                },
            }
        ],
        "youtube_trending": [
            {
                "id": "yt_trending:MOCKID1",
                "title": f"Top trending: {subquery.search_query} compilation",
                "snippet": f"Best moments of {subquery.search_query} this month.",
                "url": "https://www.youtube.com/watch?v=MOCKID1",
                "source_domain": "youtube.com",
                "author": "MockChannel",
                "date": dates.get_date_range(3)[0],
                "relevance": 0.7,
                "why_relevant": f"YouTube trending: {subquery.search_query} compilation",
                "engagement_score": 1234567.0,
                "metadata": {
                    "video_id": "MOCKID1",
                    "channel": "MockChannel",
                    "view_count": 1234567,
                    "like_count": 45000,
                    "region": "US",
                },
            }
        ],
        "soovle": [
            {
                "id": f"soovle:google:0:{subquery.search_query}",
                "title": f"{subquery.search_query} review",
                "snippet": "Google autocomplete suggestion",
                "url": f"https://soovle.com/?q={subquery.search_query}",
                "source_domain": "soovle.com",
                "date": dates.get_date_range(1)[0],
                "relevance": 0.55,
                "why_relevant": f"Soovle google autocomplete: {subquery.search_query} review",
                "metadata": {"engine": "google", "query": subquery.search_query},
            }
        ],
        "answer_socrates": [
            {
                "id": f"socrates:what:what is {subquery.search_query}",
                "title": f"what is {subquery.search_query}",
                "snippet": "What question from AnswerSocrates",
                "url": f"https://answersocrates.com/?q={subquery.search_query}",
                "source_domain": "answersocrates.com",
                "date": dates.get_date_range(1)[0],
                "relevance": 0.6,
                "why_relevant": f"Question demand: what is {subquery.search_query}",
                "metadata": {"question_prefix": "what", "query": subquery.search_query},
            }
        ],
        "keyword_sheeter": [
            {
                "id": f"sheeter:{subquery.search_query} for sale",
                "title": f"{subquery.search_query} for sale",
                "snippet": "Google autocomplete expansion",
                "url": f"https://keywordsheeter.com/?q={subquery.search_query}",
                "source_domain": "keywordsheeter.com",
                "date": dates.get_date_range(1)[0],
                "relevance": 0.55,
                "why_relevant": f"Long-tail keyword: {subquery.search_query} for sale",
                "metadata": {"query": subquery.search_query},
            }
        ],
        "sparktoro": [
            {
                "id": f"sparktoro:Audience overlap for {subquery.search_query}",
                "title": f"Top podcast for {subquery.search_query} fans",
                "snippet": "Audience overlap: 87.5",
                "url": "https://sparktoro.com/search",
                "source_domain": "sparktoro.com",
                "date": dates.get_date_range(5)[0],
                "relevance": 0.7,
                "why_relevant": f"SparkToro audience overlap: top podcast",
                "engagement_score": 87.5,
                "metadata": {"overlap_score": 87.5, "type": "podcast"},
            }
        ],
        "exploding_topics": [
            {
                "id": f"exploding:{subquery.search_query} alternatives",
                "title": f"{subquery.search_query} alternatives",
                "snippet": "Exploding Topics — growth +320.0%",
                "url": f"https://explodingtopics.com/topic/{subquery.search_query}-alternatives",
                "source_domain": "explodingtopics.com",
                "date": dates.get_date_range(5)[0],
                "relevance": 0.7,
                "why_relevant": f"Emerging trend: {subquery.search_query} alternatives",
                "engagement_score": 320.0,
                "metadata": {"growth_rate": 320.0, "category": "tech"},
            }
        ],
        "answerthepublic": [
            {
                "id": f"atp:how to use {subquery.search_query}",
                "title": f"how to use {subquery.search_query}",
                "snippet": "AnswerThePublic question [how]",
                "url": f"https://answerthepublic.com/reports/search?q={subquery.search_query}",
                "source_domain": "answerthepublic.com",
                "date": dates.get_date_range(3)[0],
                "relevance": 0.65,
                "why_relevant": f"Question demand: how to use {subquery.search_query}",
                "engagement_score": 8100.0,
                "metadata": {"volume": 8100, "category": "how"},
            }
        ],
        "alsoasked": [
            {
                "id": f"alsoasked:what are the best {subquery.search_query}",
                "title": f"what are the best {subquery.search_query}",
                "snippet": "People Also Ask question",
                "url": f"https://alsoasked.com/results?q={subquery.search_query}",
                "source_domain": "alsoasked.com",
                "date": dates.get_date_range(3)[0],
                "relevance": 0.65,
                "why_relevant": f"PAA question: what are the best {subquery.search_query}",
                "metadata": {"depth": 1},
            }
        ],
        "glimpse": [
            {
                "id": f"glimpse:{subquery.search_query} 2026",
                "title": f"{subquery.search_query} 2026",
                "snippet": "Glimpse emerging trend — 50,000 searches/mo, +180% growth",
                "url": f"https://meetglimpse.com/trend/{subquery.search_query}-2026",
                "source_domain": "meetglimpse.com",
                "date": dates.get_date_range(5)[0],
                "relevance": 0.7,
                "why_relevant": f"Emerging trend: {subquery.search_query} 2026",
                "engagement_score": 180.0,
                "metadata": {"growth_rate": 180.0, "volume": 50000},
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.14 — Non-Amazon marketplaces)
        "etsy": [
            {
                "id": "etsy:1234567890",
                "title": f"Handmade {subquery.search_query}",
                "snippet": "Etsy listing — USD 45.00, 1,500 views, 42 favorites",
                "url": "https://www.etsy.com/listing/1234567890",
                "source_domain": "etsy.com",
                "date": dates.get_date_range(5)[0],
                "relevance": 0.7,
                "why_relevant": f"Etsy marketplace match for '{subquery.search_query}'",
                "engagement_score": 1920.0,
                "metadata": {
                    "listing_id": 1234567890,
                    "shop_id": 789,
                    "price": 45.0,
                    "currency": "USD",
                    "views": 1500,
                    "favorites": 42,
                    "tags": ["handmade", "artisan"],
                },
            }
        ],
        "pinterest_commerce": [
            {
                "id": "pinterest_pin:PINMOCK1",
                "title": f"{subquery.search_query} inspiration",
                "snippet": "Pinterest pin — 500 saves, 25,000 impressions",
                "url": "https://www.pinterest.com/pin/PINMOCK1/",
                "source_domain": "pinterest.com",
                "date": dates.get_date_range(3)[0],
                "relevance": 0.65,
                "why_relevant": f"Pinterest commerce match for '{subquery.search_query}'",
                "engagement_score": 27500.0,
                "metadata": {
                    "pin_id": "PINMOCK1",
                    "board_id": "B1",
                    "saves": 500,
                    "impressions": 25000,
                },
            }
        ],
        "amazon_vendor": [
            {
                "id": "vendor:B00VENDORA",
                "title": f"1P vendor catalog: {subquery.search_query}",
                "snippet": "Brand: ExampleBrand · Category: Sports & Outdoors",
                "url": "https://www.amazon.com/dp/B00VENDORA",
                "source_domain": "amazon.com",
                "date": dates.get_date_range(7)[0],
                "relevance": 0.78,
                "why_relevant": f"Vendor Central catalog match for '{subquery.search_query}'",
                "metadata": {
                    "asin": "B00VENDORA",
                    "brand": "ExampleBrand",
                    "category": "Sports & Outdoors",
                    "business_relationship": "1P_vendor",
                },
            }
        ],
        "walmart_marketplace": [
            {
                "id": "walmart_mp:WMSKU123",
                "title": f"{subquery.search_query} at Walmart",
                "snippet": "Walmart Marketplace — brand: ExampleBrand, price: $49.99",
                "url": "https://www.walmart.com/ip/WMSKU123",
                "source_domain": "walmart.com",
                "date": dates.get_date_range(5)[0],
                "relevance": 0.72,
                "why_relevant": f"Walmart Marketplace match for '{subquery.search_query}'",
                "metadata": {
                    "sku": "WMSKU123",
                    "brand": "ExampleBrand",
                    "price": 49.99,
                    "marketplace": "walmart_us",
                },
            }
        ],
        "walmart_connect": [
            {
                "id": "walmart_connect:CAMP_MOCK_1",
                "title": f"Walmart Connect: {subquery.search_query} - Exact",
                "snippet": "Walmart Connect campaign — status: enabled, budget: $75.00",
                "url": "https://advertising.walmart.com/cm/campaigns/CAMP_MOCK_1",
                "source_domain": "advertising.walmart.com",
                "date": dates.get_date_range(3)[0],
                "relevance": 0.68,
                "why_relevant": f"Walmart Connect campaign match for '{subquery.search_query}'",
                "metadata": {
                    "campaign_id": "CAMP_MOCK_1",
                    "status": "enabled",
                    "budget": 75.0,
                },
            }
        ],
        "tiktok_shop_seller": [
            {
                "id": "tiktok_shop_seller:PRODTTS1",
                "title": f"TikTok Shop seller: {subquery.search_query}",
                "snippet": "TikTok Shop seller product — brand: BrandX, price: $55.00, status: live",
                "url": "https://shop.tiktok.com/view/product/PRODTTS1",
                "source_domain": "shop.tiktok.com",
                "date": dates.get_date_range(2)[0],
                "relevance": 0.7,
                "why_relevant": f"TikTok Shop seller match for '{subquery.search_query}'",
                "metadata": {
                    "product_id": "PRODTTS1",
                    "brand": "BrandX",
                    "price": 55.0,
                    "status": "live",
                    "business_side": "seller_partner",
                },
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.15 — Patents/Legal/Regulatory)
        "federal_register": [
            {
                "id": "fedreg:2026-MOCK1",
                "title": f"Proposed rule: {subquery.search_query} labeling requirements",
                "snippet": "Mock Federal Register document. Proposed rule from the EPA.",
                "url": "https://www.federalregister.gov/documents/2026-MOCK1",
                "source_domain": "federalregister.gov",
                "date": dates.get_date_range(5)[0],
                "relevance": 0.7,
                "why_relevant": "Federal Register proposed rule (Environmental Protection Agency)",
                "metadata": {
                    "document_number": "2026-MOCK1",
                    "document_type": "Proposed Rule",
                    "agencies": ["Environmental Protection Agency"],
                    "publication_date": dates.get_date_range(5)[0],
                },
            }
        ],
        "fda_openfda": [
            {
                "id": "openfda:RPTMOCK1",
                "title": f"Adverse event report: {subquery.search_query}",
                "snippet": "Mock openFDA record. Reason: contamination · Class: Class II",
                "url": "https://open.fda.gov/apis/RPTMOCK1",
                "source_domain": "fda.gov",
                "date": dates.get_date_range(7)[0],
                "relevance": 0.7,
                "why_relevant": f"FDA record for '{subquery.search_query}'",
                "metadata": {
                    "record_id": "RPTMOCK1",
                    "dataset": "drug/event",
                    "classification": "Class II",
                    "recall_number": "",
                },
            }
        ],
        "courtlistener": [
            {
                "id": "courtlistener:MOCKCASE1",
                "title": f"Smith v. {subquery.search_query} Corp",
                "snippet": "Mock court opinion concerning product safety.",
                "url": "https://www.courtlistener.com/opinion/MOCKCASE1/smith-v-x-corp/",
                "source_domain": "courtlistener.com",
                "date": dates.get_date_range(20)[0],
                "relevance": 0.7,
                "why_relevant": f"Court opinion matching '{subquery.search_query}'",
                "metadata": {
                    "court": "scotus",
                    "citation": "600 U.S. 123",
                    "docket_number": "23-1234",
                    "filed_date": dates.get_date_range(20)[0],
                },
            }
        ],
        "uspto_patents": [
            {
                "id": "uspto:US11111111",
                "title": f"Improved {subquery.search_query} apparatus",
                "snippet": "Mock USPTO patent abstract describing novel apparatus.",
                "url": "https://patents.google.com/patent/USUS11111111",
                "source_domain": "uspto.gov",
                "date": dates.get_date_range(25)[0],
                "author": "Example Corp",
                "relevance": 0.7,
                "why_relevant": f"USPTO patent match for '{subquery.search_query}'",
                "metadata": {
                    "patent_id": "US11111111",
                    "patent_number": "US11111111",
                    "assignees": ["Example Corp"],
                    "inventors": ["Alice Smith"],
                    "patent_date": dates.get_date_range(25)[0],
                },
            }
        ],
        "epo_ops": [
            {
                "id": "epo:EP1234567A1",
                "title": "EP1234567A1 (European patent reference)",
                "snippet": "EPO publication EP1234567A1 — EP Office, filed "
                            f"{dates.get_date_range(15)[0]}",
                "url": "https://worldwide.espacenet.com/patent/search?q=EP1234567A1",
                "source_domain": "epo.org",
                "date": dates.get_date_range(15)[0],
                "relevance": 0.7,
                "why_relevant": f"EPO patent reference for '{subquery.search_query}'",
                "metadata": {
                    "publication_id": "EP1234567A1",
                    "country": "EP",
                    "doc_number": "1234567",
                    "kind_code": "A1",
                },
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.16 — Meta Ad Library)
        "meta_ad_library": [
            {
                "id": "meta_ad:MOCKAD1",
                "title": f"Premium {subquery.search_query}",
                "snippet": f"Premium {subquery.search_query} · Best in class "
                           f"· Platforms: facebook, instagram · Started "
                           f"{dates.get_date_range(14)[0]}",
                "url": "https://www.facebook.com/ads/library/?id=MOCKAD1",
                "source_domain": "facebook.com",
                "date": dates.get_date_range(14)[0],
                "author": "Mock Advertiser",
                "relevance": 0.75,
                "why_relevant": f"Meta ad by Mock Advertiser (matching '{subquery.search_query}')",
                "metadata": {
                    "ad_id": "MOCKAD1",
                    "page_id": "MOCKPAGE1",
                    "page_name": "Mock Advertiser",
                    "platforms": ["facebook", "instagram"],
                    "delivery_start": f"{dates.get_date_range(14)[0]}T00:00:00+0000",
                    "delivery_stop": "",
                    "spend_range": "",
                    "impressions_range": "",
                    "currency": "",
                    "languages": ["en"],
                    "creative_body_count": 1,
                },
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.16.1 — Google Ads Transparency)
        "google_ads_transparency": [
            {
                "id": "google_ads:CRMOCK1",
                "title": f"Premium {subquery.search_query}",
                "snippet": f"Premium {subquery.search_query} · Free shipping · "
                           f"Regions: US, CA · First shown: {dates.get_date_range(10)[0]} · Format: IMAGE",
                "url": "https://adstransparency.google.com/advertiser/AR0001/creative/CRMOCK1",
                "source_domain": "adstransparency.google.com",
                "date": dates.get_date_range(10)[0],
                "author": "Mock Advertiser Inc.",
                "relevance": 0.75,
                "why_relevant": f"Google ad by Mock Advertiser Inc. (matching '{subquery.search_query}')",
                "metadata": {
                    "ad_id": "CRMOCK1",
                    "advertiser_id": "AR0001",
                    "advertiser_name": "Mock Advertiser Inc.",
                    "format": "IMAGE",
                    "regions": ["US", "CA"],
                    "first_shown": f"{dates.get_date_range(10)[0]}T00:00:00Z",
                    "last_shown": "",
                    "landing_page": "https://example.com/product",
                },
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.16.2 — TikTok Ads Library)
        "tiktok_ads_library": [
            {
                "id": "tiktok_ads:TTMOCK1",
                "title": f"Viral {subquery.search_query} moment",
                "snippet": f"Best {subquery.search_query} for summer · Countries: US, DE · "
                           f"First shown: {dates.get_date_range(8)[0]} · Format: VIDEO",
                "url": "https://library.tiktok.com/ads/detail/TTMOCK1",
                "source_domain": "library.tiktok.com",
                "date": dates.get_date_range(8)[0],
                "author": "Mock TikTok Advertiser",
                "relevance": 0.7,
                "why_relevant": f"TikTok ad by Mock TikTok Advertiser (matching '{subquery.search_query}')",
                "metadata": {
                    "ad_id": "TTMOCK1",
                    "advertiser_id": "TTADV001",
                    "advertiser_name": "Mock TikTok Advertiser",
                    "format": "VIDEO",
                    "countries": ["US", "DE"],
                    "first_shown": f"{dates.get_date_range(8)[0]}T00:00:00Z",
                    "last_shown": "",
                    "landing_page": "https://example.com/product",
                    "thumbnail_url": "https://example.com/thumb.jpg",
                },
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.16.3 — LinkedIn Ad Library)
        "linkedin_ad_library": [
            {
                "id": "linkedin_ad:LIMOCK1",
                "title": f"Transform your {subquery.search_query} strategy",
                "snippet": f"Transform your {subquery.search_query} strategy · Countries: US · "
                           f"Started: {dates.get_date_range(12)[0]} · Spend: USD 1000-4999 · "
                           f"Impressions: 10000-49999",
                "url": "https://www.linkedin.com/ad-library/detail/LIMOCK1",
                "source_domain": "linkedin.com",
                "date": dates.get_date_range(12)[0],
                "author": "Mock B2B SaaS Corp",
                "relevance": 0.7,
                "why_relevant": f"LinkedIn ad by Mock B2B SaaS Corp (matching '{subquery.search_query}')",
                "metadata": {
                    "ad_id": "LIMOCK1",
                    "advertiser_urn": "urn:li:organization:987654",
                    "company_id": "987654",
                    "advertiser_name": "Mock B2B SaaS Corp",
                    "countries": ["US"],
                    "delivery_start": f"{dates.get_date_range(12)[0]}T00:00:00Z",
                    "delivery_stop": "",
                    "spend_range": "USD 1000-4999",
                    "impressions_range": "10000-49999",
                },
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.16.4 — Wayback Machine CDX)
        "wayback_machine_cdx": [
            {
                "id": "wayback:20260301120000:MOCKDIGEST1",
                "title": f"https://example.com/{subquery.search_query} @ 2026-03-01",
                "snippet": "text/html · HTTP 200 · 12345 bytes",
                "url": f"https://web.archive.org/web/20260301120000/https://example.com/{subquery.search_query}",
                "source_domain": "web.archive.org",
                "date": "2026-03-01",
                "relevance": 0.65,
                "why_relevant": f"Historical snapshot of https://example.com/{subquery.search_query}",
                "metadata": {
                    "snapshot_timestamp": "20260301120000",
                    "original_url": f"https://example.com/{subquery.search_query}",
                    "mimetype": "text/html",
                    "statuscode": "200",
                    "digest": "MOCKDIGEST1",
                    "length": "12345",
                    "archive_url": f"https://web.archive.org/web/20260301120000/https://example.com/{subquery.search_query}",
                },
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.17.0 — Review aggregation)
        "app_store_reviews": [
            {
                "id": "app_store:mock:review:MOCK1",
                "title": f"{subquery.search_query} — 5 stars",
                "snippet": f"Love this {subquery.search_query} app, works perfectly.",
                "url": "https://apps.apple.com/us/app/id123456789",
                "source_domain": "apps.apple.com",
                "date": "2026-03-01",
                "author": "MockUser",
                "relevance": 0.7,
                "why_relevant": f"App Store review for '{subquery.search_query}'",
                "metadata": {
                    "star_rating": 5.0,
                    "platform": "app_store",
                    "app_id": "123456789",
                    "country": "us",
                },
            }
        ],
        "yelp_fusion": [
            {
                "id": "yelp:mock-biz-1:YMOCK1",
                "title": f"5★ review of Mock Biz ({subquery.search_query})",
                "snippet": f"Great {subquery.search_query} experience, highly recommend.",
                "url": "https://www.yelp.com/biz/mock-biz-1",
                "source_domain": "yelp.com",
                "date": "2026-03-01",
                "author": "Jane D.",
                "relevance": 0.7,
                "why_relevant": f"Yelp review of 'Mock Biz' matching '{subquery.search_query}'",
                "metadata": {
                    "star_rating": 5.0,
                    "platform": "yelp",
                    "business_id": "mock-biz-1",
                    "business_name": "Mock Biz",
                },
            }
        ],
        "trustpilot": [
            {
                "id": "trustpilot:example.com:summary",
                "title": f"Trustpilot aggregate for {subquery.search_query}",
                "snippet": f"4.3★ ({12000} reviews) on Trustpilot",
                "url": "https://www.trustpilot.com/review/example.com",
                "source_domain": "trustpilot.com",
                "date": "2026-03-01",
                "relevance": 0.65,
                "why_relevant": f"Trustpilot rating summary for '{subquery.search_query}'",
                "metadata": {
                    "star_rating": 4.3,
                    "review_count": 12000,
                    "platform": "trustpilot",
                    "summary_only": True,
                },
            }
        ],
        "g2": [
            {
                "id": "g2:mock-product:summary",
                "title": f"G2 aggregate for {subquery.search_query}",
                "snippet": f"4.4★ ({500} reviews) on G2",
                "url": "https://www.g2.com/products/mock-product/reviews",
                "source_domain": "g2.com",
                "date": "2026-03-01",
                "relevance": 0.65,
                "why_relevant": f"G2 rating summary for '{subquery.search_query}'",
                "metadata": {
                    "star_rating": 4.4,
                    "review_count": 500,
                    "platform": "g2",
                    "category": "saas",
                    "summary_only": True,
                },
            }
        ],
        "capterra": [
            {
                "id": "capterra:12345/mock-product:summary",
                "title": f"Capterra aggregate for {subquery.search_query}",
                "snippet": f"4.5★ ({800} reviews) on Capterra",
                "url": "https://www.capterra.com/p/12345/mock-product/reviews/",
                "source_domain": "capterra.com",
                "date": "2026-03-01",
                "relevance": 0.65,
                "why_relevant": f"Capterra rating summary for '{subquery.search_query}'",
                "metadata": {
                    "star_rating": 4.5,
                    "review_count": 800,
                    "platform": "capterra",
                    "category": "saas",
                    "summary_only": True,
                },
            }
        ],
        "google_play_reviews": [
            {
                "id": "google_play:com.example.app:summary",
                "title": f"Google Play aggregate for {subquery.search_query}",
                "snippet": f"4.6★ ({50000} reviews) on Google Play",
                "url": "https://play.google.com/store/apps/details?id=com.example.app",
                "source_domain": "play.google.com",
                "date": "2026-03-01",
                "relevance": 0.65,
                "why_relevant": f"Google Play rating summary for '{subquery.search_query}'",
                "metadata": {
                    "star_rating": 4.6,
                    "review_count": 50000,
                    "platform": "google_play",
                    "package_name": "com.example.app",
                    "summary_only": True,
                },
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.18.0 — Financial markets)
        "fred": [
            {
                "id": "fred:GDP",
                "title": f"FRED series related to {subquery.search_query}",
                "snippet": "Quarterly GDP series (mock)",
                "url": "https://fred.stlouisfed.org/series/GDP",
                "source_domain": "fred.stlouisfed.org",
                "date": "2026-03-01",
                "relevance": 0.7,
                "why_relevant": f"FRED series for '{subquery.search_query}'",
                "metadata": {"platform": "fred", "symbol": "GDP", "asset_type": "economic_indicator"},
            }
        ],
        "alpha_vantage": [
            {
                "id": "alphavantage:AAPL",
                "title": f"AAPL — {subquery.search_query} (mock)",
                "snippet": "Equity · United States · USD",
                "url": "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=AAPL",
                "source_domain": "alphavantage.co",
                "date": "2026-03-01",
                "relevance": 0.7,
                "why_relevant": f"Alpha Vantage symbol for '{subquery.search_query}'",
                "metadata": {"platform": "alpha_vantage", "symbol": "AAPL", "asset_type": "equity", "currency": "USD"},
            }
        ],
        "polygon_io": [
            {
                "id": "polygon:AAPL",
                "title": f"AAPL — {subquery.search_query} (mock)",
                "snippet": "stocks · CS · NASDAQ",
                "url": "https://polygon.io/quote/AAPL",
                "source_domain": "polygon.io",
                "date": "2026-03-01",
                "relevance": 0.7,
                "why_relevant": f"Polygon.io ticker for '{subquery.search_query}'",
                "metadata": {"platform": "polygon_io", "symbol": "AAPL", "asset_type": "cs", "exchange": "NASDAQ"},
            }
        ],
        "finnhub": [
            {
                "id": "finnhub:AAPL",
                "title": f"AAPL — {subquery.search_query} (mock)",
                "snippet": "Common Stock",
                "url": "https://finnhub.io/stock/AAPL",
                "source_domain": "finnhub.io",
                "date": "2026-03-01",
                "relevance": 0.7,
                "why_relevant": f"Finnhub symbol for '{subquery.search_query}'",
                "metadata": {"platform": "finnhub", "symbol": "AAPL", "asset_type": "common stock"},
            }
        ],
        "sec_xbrl": [
            {
                "id": "sec_xbrl:0000320193:companyfacts",
                "title": f"Apple Inc. — SEC XBRL companyfacts (mock)",
                "snippet": "423 XBRL fact tags across us-gaap + dei taxonomies",
                "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193",
                "source_domain": "sec.gov",
                "date": "2026-03-01",
                "relevance": 0.75,
                "why_relevant": f"SEC XBRL for '{subquery.search_query}'",
                "metadata": {"platform": "sec_xbrl", "cik": "0000320193", "entity_name": "Apple Inc.", "total_fact_tags": 423},
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.19.0 — Weather/environmental)
        "noaa": [
            {
                "id": "noaa:GHCND:USW00094728",
                "title": f"NEW YORK CENTRAL PARK (mock for '{subquery.search_query}')",
                "snippet": "GHCND:USW00094728 · elevation 42.7 METERS",
                "url": "https://www.ncei.noaa.gov/cdo-web/datasets/GHCND/stations/GHCND:USW00094728/detail",
                "source_domain": "ncei.noaa.gov",
                "date": "2026-03-01",
                "relevance": 0.7,
                "why_relevant": f"NOAA weather station mock for '{subquery.search_query}'",
                "metadata": {"platform": "noaa", "station_id": "GHCND:USW00094728", "location": "NEW YORK CENTRAL PARK"},
            }
        ],
        "openweather": [
            {
                "id": "openweather:5128581",
                "title": f"New York — Clear (mock for '{subquery.search_query}')",
                "snippet": "68.2° · clear sky · humidity 55%",
                "url": "https://openweathermap.org/city/5128581",
                "source_domain": "openweathermap.org",
                "date": "2026-03-01",
                "relevance": 0.7,
                "why_relevant": f"OpenWeather current conditions mock for '{subquery.search_query}'",
                "metadata": {"platform": "openweather", "station_id": "5128581", "location": "New York", "value": 68.2, "unit": "°"},
            }
        ],
        "epa_airnow": [
            {
                "id": "epa_airnow:Manhattan:O3:2026-03-01",
                "title": f"Manhattan, NY — AQI 45 (O3) (mock for '{subquery.search_query}')",
                "snippet": "Good · AQI 45 for O3",
                "url": "https://www.airnow.gov/",
                "source_domain": "airnow.gov",
                "date": "2026-03-01",
                "relevance": 0.7,
                "why_relevant": f"EPA AirNow AQI mock for '{subquery.search_query}'",
                "metadata": {"platform": "epa_airnow", "location": "Manhattan, NY", "value": 45, "unit": "AQI"},
            }
        ],
        "nasa_power": [
            {
                "id": "nasa_power:40.7128:-74.006:T2M:20260301",
                "title": f"NASA POWER T2M @ (40.7128, -74.006) (mock for '{subquery.search_query}')",
                "snippet": "T2M: 35.8 on 2026-03-01",
                "url": "https://power.larc.nasa.gov/data-access-viewer/",
                "source_domain": "power.larc.nasa.gov",
                "date": "2026-03-01",
                "relevance": 0.7,
                "why_relevant": f"NASA POWER meteorology mock for '{subquery.search_query}'",
                "metadata": {"platform": "nasa_power", "location": "40.7128,-74.006", "value": 35.8, "measurement_type": "t2m"},
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.20.0 — News aggregation)
        "google_news": [
            {
                "id": "google_news:https://example.com/a",
                "title": f"Mock news article about {subquery.search_query}",
                "snippet": "Example snippet from Google News feed",
                "url": "https://example.com/a",
                "source_domain": "example.com",
                "date": "2026-03-01",
                "relevance": 0.65,
                "why_relevant": f"Google News mock for '{subquery.search_query}'",
                "metadata": {"platform": "google_news", "publisher": "Example"},
            }
        ],
        "newsapi": [
            {
                "id": "newsapi:https://example.com/a",
                "title": f"NewsAPI article about {subquery.search_query}",
                "snippet": "NewsAPI description",
                "url": "https://example.com/a",
                "source_domain": "example",
                "date": "2026-03-01",
                "relevance": 0.68,
                "why_relevant": f"NewsAPI mock for '{subquery.search_query}'",
                "metadata": {"platform": "newsapi", "publisher": "Example"},
            }
        ],
        "gdelt": [
            {
                "id": "gdelt:https://example.com/a",
                "title": f"GDELT article about {subquery.search_query}",
                "snippet": "",
                "url": "https://example.com/a",
                "source_domain": "example.com",
                "date": "2026-03-01",
                "relevance": 0.65,
                "why_relevant": f"GDELT mock for '{subquery.search_query}'",
                "metadata": {"platform": "gdelt", "sourcecountry": "US"},
            }
        ],
        "mediacloud": [
            {
                "id": "mediacloud:99",
                "title": f"MediaCloud story about {subquery.search_query}",
                "snippet": "MediaCloud story description",
                "url": "https://example.com/a",
                "source_domain": "Example",
                "date": "2026-03-01",
                "relevance": 0.68,
                "why_relevant": f"MediaCloud mock for '{subquery.search_query}'",
                "metadata": {"platform": "mediacloud", "stories_id": 99, "media_name": "Example"},
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.21.0 — Developer signals)
        "npm_registry": [
            {
                "id": f"npm:mock-{subquery.search_query}",
                "title": f"mock-{subquery.search_query} — Mock npm package",
                "snippet": "v1.0.0 · keywords",
                "url": f"https://www.npmjs.com/package/mock-{subquery.search_query}",
                "source_domain": "npmjs.com",
                "date": "2026-03-01",
                "relevance": 0.75,
                "why_relevant": f"npm mock for '{subquery.search_query}'",
                "metadata": {"platform": "npm", "package_name": f"mock-{subquery.search_query}", "version": "1.0.0"},
            }
        ],
        "pypi": [
            {
                "id": f"pypi:{subquery.search_query}",
                "title": f"{subquery.search_query} 1.0.0 — Mock PyPI package",
                "snippet": "Mock PyPI summary",
                "url": f"https://pypi.org/project/{subquery.search_query}/",
                "source_domain": "pypi.org",
                "date": "2026-03-01",
                "relevance": 0.7,
                "why_relevant": f"PyPI mock for '{subquery.search_query}'",
                "metadata": {"platform": "pypi", "package_name": subquery.search_query, "version": "1.0.0"},
            }
        ],
        "homebrew": [
            {
                "id": f"homebrew:{subquery.search_query}",
                "title": f"{subquery.search_query} — Mock Homebrew formula",
                "snippet": "Mock formula description",
                "url": f"https://formulae.brew.sh/formula/{subquery.search_query}",
                "source_domain": "brew.sh",
                "date": None,
                "relevance": 0.7,
                "why_relevant": f"Homebrew mock for '{subquery.search_query}'",
                "metadata": {"platform": "homebrew", "formula_name": subquery.search_query},
            }
        ],
        "docker_hub": [
            {
                "id": f"dockerhub:{subquery.search_query}",
                "title": f"{subquery.search_query} — Mock Docker image",
                "snippet": "Mock image description",
                "url": f"https://hub.docker.com/r/{subquery.search_query}",
                "source_domain": "hub.docker.com",
                "date": None,
                "relevance": 0.7,
                "why_relevant": f"Docker Hub mock for '{subquery.search_query}'",
                "metadata": {"platform": "docker_hub", "repo_name": subquery.search_query, "is_official": False},
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.22.0 — Crypto/on-chain)
        "coingecko": [
            {
                "id": "coingecko:bitcoin",
                "title": f"BTC — Bitcoin (mock for '{subquery.search_query}')",
                "snippet": "Market cap rank: 1",
                "url": "https://www.coingecko.com/en/coins/bitcoin",
                "source_domain": "coingecko.com",
                "date": None,
                "relevance": 0.7,
                "why_relevant": f"CoinGecko mock for '{subquery.search_query}'",
                "metadata": {"platform": "coingecko", "coin_id": "bitcoin", "symbol": "BTC", "market_cap_rank": 1},
            }
        ],
        "defillama": [
            {
                "id": "defillama:aave",
                "title": f"Aave — TVL $5,000,000,000 (mock for '{subquery.search_query}')",
                "snippet": "Lending · Ethereum",
                "url": "https://defillama.com/protocol/aave",
                "source_domain": "defillama.com",
                "date": None,
                "relevance": 0.7,
                "why_relevant": f"DeFiLlama mock for '{subquery.search_query}'",
                "metadata": {"platform": "defillama", "protocol_name": "Aave", "category": "Lending", "tvl_usd": 5e9},
            }
        ],
        "etherscan": [
            {
                "id": "etherscan:balance:1000000000000000000",
                "title": "ETH balance — 1.0 ETH (mock)",
                "snippet": "Mock balance",
                "url": "https://etherscan.io/",
                "source_domain": "etherscan.io",
                "date": None,
                "relevance": 0.7,
                "why_relevant": f"Etherscan balance mock for '{subquery.search_query}'",
                "metadata": {"platform": "etherscan", "balance_eth": 1.0},
            }
        ],
        "dune": [
            {
                "id": "dune:query:12345:results",
                "title": f"Dune query 12345 — 42 rows (mock)",
                "snippet": "Dune mock row data",
                "url": "https://dune.com/queries/12345",
                "source_domain": "dune.com",
                "date": None,
                "relevance": 0.7,
                "why_relevant": f"Dune mock for '{subquery.search_query}'",
                "metadata": {"platform": "dune", "query_id": "12345", "row_count": 42},
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.23.0 — Federated social)
        "mastodon": [
            {
                "id": "mastodon:mock1",
                "title": f"@mockuser — mock post about {subquery.search_query}",
                "snippet": f"Mock mastodon post about {subquery.search_query}",
                "url": "https://mastodon.social/@mockuser/mock1",
                "source_domain": "mastodon.social",
                "date": "2026-03-01",
                "author": "mockuser",
                "relevance": 0.65,
                "why_relevant": f"Mastodon mock for '{subquery.search_query}'",
                "metadata": {"platform": "mastodon", "status_id": "mock1", "favourites_count": 10},
            }
        ],
        "lemmy": [
            {
                "id": "lemmy:1",
                "title": f"Mock lemmy post about {subquery.search_query}",
                "snippet": "Mock body",
                "url": "https://lemmy.world/post/1",
                "source_domain": "lemmy.world",
                "date": "2026-03-01",
                "author": "mockuser",
                "relevance": 0.65,
                "why_relevant": f"Lemmy mock for '{subquery.search_query}'",
                "metadata": {"platform": "lemmy", "post_id": 1, "score": 10},
            }
        ],
        "farcaster": [
            {
                "id": "farcaster:0xabc",
                "title": f"@dwr — mock cast about {subquery.search_query}",
                "snippet": f"Mock farcaster cast about {subquery.search_query}",
                "url": "https://warpcast.com/dwr/0xabc",
                "source_domain": "farcaster.xyz",
                "date": "2026-03-01",
                "author": "dwr",
                "relevance": 0.65,
                "why_relevant": f"Farcaster mock for '{subquery.search_query}'",
                "metadata": {"platform": "farcaster", "cast_hash": "0xabc", "author_fid": 3},
            }
        ],
        "discord": [
            {
                "id": "discord:msg1",
                "title": f"#c1 · @mockuser",
                "snippet": f"Mock discord message about {subquery.search_query}",
                "url": "https://discord.com/channels/g1/c1/msg1",
                "source_domain": "discord.com",
                "date": "2026-03-01",
                "author": "mockuser",
                "relevance": 0.65,
                "why_relevant": f"Discord mock for '{subquery.search_query}'",
                "metadata": {"platform": "discord", "message_id": "msg1", "channel_id": "c1", "guild_id": "g1"},
            }
        ],
        # Signalsweep-unique source mock fixtures (v3.24.0 — Geographic/Events/Gov)
        "cdc_data": [{
            "id": "cdc_data:abcd-efgh",
            "title": f"CDC dataset about {subquery.search_query}",
            "snippet": "Mock CDC dataset",
            "url": "https://data.cdc.gov/d/abcd-efgh",
            "source_domain": "data.cdc.gov",
            "date": "2026-03-01",
            "relevance": 0.7,
            "why_relevant": f"CDC mock for '{subquery.search_query}'",
            "metadata": {"platform": "cdc_data", "dataset_id": "abcd-efgh"},
        }],
        "usda_ers": [{
            "id": "usda_ers:arms:mock",
            "title": f"USDA ERS mock report",
            "snippet": "Mock ARMS survey",
            "url": "https://www.ers.usda.gov/data-products/",
            "source_domain": "ers.usda.gov",
            "date": None,
            "relevance": 0.7,
            "why_relevant": f"USDA ERS mock for '{subquery.search_query}'",
            "metadata": {"platform": "usda_ers", "row_count": 100},
        }],
        "google_places": [{
            "id": "google_places:ChIJmock",
            "title": f"Mock Place — {subquery.search_query}",
            "snippet": "4.5★ (12000 reviews) · restaurant",
            "url": "https://www.google.com/maps/place/?q=place_id:ChIJmock",
            "source_domain": "google.com",
            "date": None,
            "relevance": 0.7,
            "why_relevant": f"Google Places mock for '{subquery.search_query}'",
            "metadata": {"platform": "google_places", "place_id": "ChIJmock", "rating": 4.5},
        }],
        "foursquare": [{
            "id": "foursquare:abc",
            "title": f"Mock Foursquare Place for {subquery.search_query}",
            "snippet": "Pizza",
            "url": "https://foursquare.com/v/abc",
            "source_domain": "foursquare.com",
            "date": None,
            "relevance": 0.7,
            "why_relevant": f"Foursquare mock for '{subquery.search_query}'",
            "metadata": {"platform": "foursquare", "fsq_id": "abc"},
        }],
        "eventbrite": [{
            "id": "eventbrite:evt1",
            "title": f"Mock event for {subquery.search_query}",
            "snippet": "Mock event description",
            "url": "https://eventbrite.com/e/evt1",
            "source_domain": "eventbrite.com",
            "date": "2026-04-13",
            "relevance": 0.7,
            "why_relevant": f"Eventbrite mock for '{subquery.search_query}'",
            "metadata": {"platform": "eventbrite", "event_id": "evt1"},
        }],
        "meetup": [{
            "id": "meetup:evt1",
            "title": f"Mock Meetup for {subquery.search_query}",
            "snippet": "Mock description",
            "url": "https://meetup.com/evt1",
            "source_domain": "meetup.com",
            "date": "2026-04-13",
            "relevance": 0.7,
            "why_relevant": f"Meetup mock for '{subquery.search_query}'",
            "metadata": {"platform": "meetup", "event_id": "evt1", "group_urlname": "nypython"},
        }],
        # Signalsweep-unique source mock fixtures (v3.25.0 — Market/creator/podcast envelopes)
        "crunchbase": [{"id": "crunchbase:mock", "title": f"Mock Crunchbase for {subquery.search_query}", "snippet": "Mock", "url": "https://www.crunchbase.com/organization/mock", "source_domain": "crunchbase.com", "date": None, "relevance": 0.7, "why_relevant": "Mock", "metadata": {"platform": "crunchbase"}}],
        "similarweb": [{"id": "similarweb:example.com", "title": f"Mock Similarweb for {subquery.search_query}", "snippet": "Mock", "url": "https://www.similarweb.com/website/example.com/", "source_domain": "similarweb.com", "date": "2026-03-01", "relevance": 0.7, "why_relevant": "Mock", "metadata": {"platform": "similarweb"}}],
        "builtwith": [{"id": "builtwith:example.com", "title": f"Mock BuiltWith for {subquery.search_query}", "snippet": "Mock", "url": "https://builtwith.com/example.com", "source_domain": "builtwith.com", "date": None, "relevance": 0.7, "why_relevant": "Mock", "metadata": {"platform": "builtwith"}}],
        "buzzsumo": [{"id": "buzzsumo:mock", "title": f"Mock BuzzSumo for {subquery.search_query}", "snippet": "Mock", "url": "https://example.com/a", "source_domain": "example.com", "date": "2026-03-01", "relevance": 0.7, "why_relevant": "Mock", "metadata": {"platform": "buzzsumo"}}],
        "listen_notes": [{"id": "listen_notes:ep1", "title": f"Mock Listen Notes for {subquery.search_query}", "snippet": "Mock", "url": "https://listennotes.com/e/ep1", "source_domain": "listennotes.com", "date": None, "relevance": 0.7, "why_relevant": "Mock", "metadata": {"platform": "listen_notes"}}],
        "podchaser": [{"id": "podchaser:p1", "title": f"Mock Podchaser for {subquery.search_query}", "snippet": "Mock", "url": "https://www.podchaser.com/podcasts/p1", "source_domain": "podchaser.com", "date": None, "relevance": 0.7, "why_relevant": "Mock", "metadata": {"platform": "podchaser"}}],
        # Signalsweep-unique source mock fixtures (v3.27.0 — Latent demand signals)
        "cpsc_saferproducts": [{"id": "cpsc:R-001", "title": f"CPSC Recall: {subquery.search_query}", "snippet": "Mock CPSC recall notice", "url": "https://www.saferproducts.gov/PublicSearch/Detail/R-001", "source_domain": "saferproducts.gov", "date": dates.get_date_range(30)[0], "relevance": 0.7, "why_relevant": "Mock", "metadata": {"hazard_type": "fire", "recall_number": "R-001"}}],
        "instacart_trends": [{"id": "instacart:trend-1", "title": f"Instacart Trend: {subquery.search_query}", "snippet": "Mock grocery trend signal", "url": "https://www.instacart.com/company/data-trends/", "source_domain": "instacart.com", "date": dates.get_date_range(7)[0], "relevance": 0.6, "why_relevant": "Mock", "metadata": {"signal_type": "editorial", "data_type": "grocery_trend"}}],
        "amazon_brand_analytics": [{"id": "sqp:mock-query", "title": f"SQP: {subquery.search_query}", "snippet": "Impressions: 10,000 · Clicks: 500", "url": "https://sellercentral.amazon.com/brand-analytics/search-query-performance", "source_domain": "amazon.com", "date": None, "relevance": 0.8, "why_relevant": "Mock", "metadata": {"report_type": "search_query_performance", "impressions": 10000, "clicks": 500}}],
        "shopify_analytics": [{"id": "shopify:top_products:0", "title": f"Shopify: {subquery.search_query}", "snippet": "total_sales: 1500.00 · total_orders: 120", "url": "https://admin.shopify.com/", "source_domain": "shopify.com", "date": None, "relevance": 0.8, "why_relevant": "Mock", "metadata": {"signal_type": "store_analytics", "query_type": "top_products"}}],
        # Signalsweep-unique source mock fixtures (v3.28.0 — Dark demand signals)
        "common_crawl": [{"id": "cc:mock-1", "title": "https://example.com/page", "snippet": "Type: text/html · Status: 200", "url": "https://example.com/page", "source_domain": "example.com", "date": dates.get_date_range(30)[0], "relevance": 0.6, "why_relevant": "Mock", "metadata": {"signal_type": "web_crawl"}}],
        "google_patents": [{"id": "gpatent:US-MOCK", "title": f"Mock Patent: {subquery.search_query}", "snippet": "A novel system for...", "url": "https://patents.google.com/patent/US-MOCK", "source_domain": "patents.google.com", "date": None, "relevance": 0.7, "why_relevant": "Mock", "metadata": {"signal_type": "patent"}}],
        "nutritionix": [{"id": "nutritionix:mock-1", "title": f"Mock Nutritionix: {subquery.search_query}", "snippet": "Brand: KIND · Protein: 12g", "url": "https://www.nutritionix.com/food/mock", "source_domain": "nutritionix.com", "date": None, "relevance": 0.7, "why_relevant": "Mock", "metadata": {"signal_type": "product_attribute"}}],
        "powerreviews": [{"id": "powerreviews:mock-1", "title": "Great product", "snippet": "Rating: 4/5 · Works well", "url": "https://www.powerreviews.com/", "source_domain": "powerreviews.com", "date": None, "relevance": 0.7, "why_relevant": "Mock", "metadata": {"signal_type": "review", "star_rating": 4}}],
        "spotify_podcasts": [{"id": "spotify_ep:mock-1", "title": f"Mock Spotify: {subquery.search_query}", "snippet": "Show: Mock Pod · 45 min", "url": "https://open.spotify.com/episode/mock-1", "source_domain": "spotify.com", "date": dates.get_date_range(7)[0], "relevance": 0.7, "why_relevant": "Mock", "metadata": {"signal_type": "podcast"}}],
        "stamped_reviews": [{"id": "stamped:mock-1", "title": "Love it", "snippet": "Rating: 5/5 · Best product ever", "url": "https://stamped.io/", "source_domain": "stamped.io", "date": None, "relevance": 0.7, "why_relevant": "Mock", "metadata": {"signal_type": "review", "star_rating": 5}}],
        "aftership_returns": [{"id": "aftership_return:mock-1", "title": "Wrong color", "snippet": "Reason: Wrong color", "url": "https://accounts.aftership.com/returns", "source_domain": "aftership.com", "date": dates.get_date_range(7)[0], "relevance": 0.7, "why_relevant": "Mock", "metadata": {"signal_type": "return_event"}}],
        "gorgias_tickets": [{"id": "gorgias:mock-1", "title": "Shipping question", "snippet": "When will my order arrive?", "url": "https://app.gorgias.com/tickets/mock-1", "source_domain": "gorgias.com", "date": dates.get_date_range(7)[0], "relevance": 0.7, "why_relevant": "Mock", "metadata": {"signal_type": "support_ticket"}}],
        "klaviyo_events": [{"id": "klaviyo:mock-1", "title": f"Mock Klaviyo: Placed Order", "snippet": "Items: Protein Bar · Value: $49.99", "url": "https://www.klaviyo.com/analytics/events", "source_domain": "klaviyo.com", "date": dates.get_date_range(7)[0], "relevance": 0.7, "why_relevant": "Mock", "metadata": {"signal_type": "customer_event"}}],
        "nhtsa_complaints": [{"id": "nhtsa:mock-1", "title": f"Mock NHTSA: {subquery.search_query}", "snippet": "Vehicle lost power", "url": "https://www.nhtsa.gov/vehicle/MOCK/complaints", "source_domain": "nhtsa.gov", "date": dates.get_date_range(30)[0], "relevance": 0.7, "why_relevant": "Mock", "metadata": {"signal_type": "safety_complaint"}}],
        "cfpb_complaints": [{"id": "cfpb:mock-1", "title": f"Mock CFPB: {subquery.search_query}", "snippet": "Product: Credit card · Issue: Billing", "url": "https://www.consumerfinance.gov/data-research/consumer-complaints/search/detail/mock-1", "source_domain": "consumerfinance.gov", "date": dates.get_date_range(30)[0], "relevance": 0.7, "why_relevant": "Mock", "metadata": {"signal_type": "consumer_complaint"}}],
        "indiegogo": [{"id": "indiegogo:mock-1", "title": f"Mock Indiegogo: {subquery.search_query}", "snippet": "$50,000 / $25,000 (200%) · 800 backers", "url": "https://www.indiegogo.com/projects/mock", "source_domain": "indiegogo.com", "date": dates.get_date_range(30)[0], "relevance": 0.7, "why_relevant": "Mock", "metadata": {"signal_type": "crowdfunding", "funds_raised": 50000, "backers": 800}}],
        "kickstarter": [{"id": "kickstarter:mock-1", "title": f"Mock Kickstarter: {subquery.search_query}", "snippet": "$100,000 / $50,000 (200%) · 1,500 backers", "url": "https://www.kickstarter.com/projects/mock", "source_domain": "kickstarter.com", "date": dates.get_date_range(30)[0], "relevance": 0.7, "why_relevant": "Mock", "metadata": {"signal_type": "crowdfunding", "pledged": 100000, "backers": 1500}}],
        "loop_returns": [{"id": "loop_return:mock-1", "title": "Too small", "snippet": "Reason: Too small · Products: Shoes", "url": "https://app.loopreturns.com/", "source_domain": "loopreturns.com", "date": dates.get_date_range(7)[0], "relevance": 0.7, "why_relevant": "Mock", "metadata": {"signal_type": "return_event"}}],
        "yotpo_reviews": [{"id": "yotpo:mock-1", "title": "Great product", "snippet": "Rating: 5/5 · Verified buyer", "url": "https://www.yotpo.com/", "source_domain": "yotpo.com", "date": dates.get_date_range(7)[0], "relevance": 0.7, "why_relevant": "Mock", "metadata": {"signal_type": "review", "star_rating": 5}}],
        "open_food_facts": [{"id": "off:mock-123", "title": f"Mock OFF: {subquery.search_query}", "snippet": "Nutri-Score: B · Protein: 10g/100g", "url": "https://world.openfoodfacts.org/product/mock-123", "source_domain": "openfoodfacts.org", "date": None, "relevance": 0.7, "why_relevant": "Mock", "metadata": {"signal_type": "product_attribute", "nutriscore_grade": "b"}}],
        "usda_fooddata": [{"id": "fdc:mock-1", "title": f"Mock USDA: {subquery.search_query}", "snippet": "Protein: 23g · Energy: 120 kcal", "url": "https://fdc.nal.usda.gov/fdc-app.html#/food-details/mock-1/nutrients", "source_domain": "fdc.nal.usda.gov", "date": None, "relevance": 0.7, "why_relevant": "Mock", "metadata": {"signal_type": "product_attribute", "protein_g": 23}}],
    }
    if source == "grounding":
        return payloads.get(source, []), {
            "label": subquery.label,
            "mock": True,
            "webSearchQueries": [subquery.search_query],
            "resultCount": 1,
        }
    return payloads.get(source, []), {}
