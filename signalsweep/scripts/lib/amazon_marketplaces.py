"""Amazon marketplace metadata — single source of truth (signalsweep 3.7.2+).

Surfaces the region-multiplexing capability shipped in v3.7 (via `keepa.py`,
`sp_api.py`, `ads_api.py`) as a single, documented constant map. 23 Amazon
marketplaces supported by SP-API as of 2026-04-13 — 12 of them also covered
by Keepa's product catalog API.

Values verified at ship-time against:
  - SP-API Marketplace IDs: developer-docs.amazon.com/sp-api/docs/marketplace-ids
  - SP-API Endpoints: developer-docs.amazon.com/sp-api/docs/sp-api-endpoints
  - Keepa AmazonLocale enum: github.com/keepacom/api_backend (AmazonLocale.java)

Re-verify if Amazon or Keepa publish updates.

**Scope:** pure data + helper functions. No HTTP, no mutation, no state.
Consumed by keepa.py, sp_api.py, ads_api.py via the helpers defined here.

Note on IN (India): SP-API marketplace-ids page labels India's region as "AP",
but the SP-API endpoints page lists only NA/EU/FE. We route India through FE
to match current v3.7 behavior; revisit if Amazon publishes an AP endpoint.
"""

from __future__ import annotations

from typing import Any


SP_API_ENDPOINTS: dict[str, str] = {
    "NA": "https://sellingpartnerapi-na.amazon.com",
    "EU": "https://sellingpartnerapi-eu.amazon.com",
    "FE": "https://sellingpartnerapi-fe.amazon.com",
}

# Amazon Ads API uses a different hostname pattern than SP-API.
# Same NA/EU/FE cluster scheme; different endpoint base URLs.
ADS_API_ENDPOINTS: dict[str, str] = {
    "NA": "https://advertising-api.amazon.com",
    "EU": "https://advertising-api-eu.amazon.com",
    "FE": "https://advertising-api-fe.amazon.com",
}


# Each entry keyed by 2-letter ISO-3166 country code (Amazon SP-API convention).
# Fields:
#   sp_api_marketplace_id — Amazon's per-marketplace identifier
#   keepa_domain_id       — Keepa's domain number (None if Keepa doesn't cover)
#   sp_api_region         — NA | EU | FE; routes to the right sellingpartnerapi-*.amazon.com endpoint
#   sp_api_endpoint       — fully-qualified base URL (mirrors sp_api_region)
#   currency              — ISO 4217 code (informational; not consumed by current adapters)
#   locale                — BCP-47 (e.g., "de-DE")
#   tld                   — amazon.<tld> path segment (e.g., "co.uk", "de", "com.mx")
#   country_name          — human-readable
MARKETPLACES: dict[str, dict[str, Any]] = {
    # North America
    "US": {
        "sp_api_marketplace_id": "ATVPDKIKX0DER",
        "keepa_domain_id": 1,
        "sp_api_region": "NA",
        "sp_api_endpoint": SP_API_ENDPOINTS["NA"],
        "currency": "USD",
        "locale": "en-US",
        "tld": "com",
        "country_name": "United States",
    },
    "CA": {
        "sp_api_marketplace_id": "A2EUQ1WTGCTBG2",
        "keepa_domain_id": 6,
        "sp_api_region": "NA",
        "sp_api_endpoint": SP_API_ENDPOINTS["NA"],
        "currency": "CAD",
        "locale": "en-CA",
        "tld": "ca",
        "country_name": "Canada",
    },
    "MX": {
        "sp_api_marketplace_id": "A1AM78C64UM0Y8",
        "keepa_domain_id": 11,
        "sp_api_region": "NA",
        "sp_api_endpoint": SP_API_ENDPOINTS["NA"],
        "currency": "MXN",
        "locale": "es-MX",
        "tld": "com.mx",
        "country_name": "Mexico",
    },
    "BR": {
        "sp_api_marketplace_id": "A2Q3Y263D00KWC",
        "keepa_domain_id": 12,
        "sp_api_region": "NA",
        "sp_api_endpoint": SP_API_ENDPOINTS["NA"],
        "currency": "BRL",
        "locale": "pt-BR",
        "tld": "com.br",
        "country_name": "Brazil",
    },
    # Europe / EMEA cluster
    "UK": {
        "sp_api_marketplace_id": "A1F83G8C2ARO7P",
        "keepa_domain_id": 2,
        "sp_api_region": "EU",
        "sp_api_endpoint": SP_API_ENDPOINTS["EU"],
        "currency": "GBP",
        "locale": "en-GB",
        "tld": "co.uk",
        "country_name": "United Kingdom",
    },
    "DE": {
        "sp_api_marketplace_id": "A1PA6795UKMFR9",
        "keepa_domain_id": 3,
        "sp_api_region": "EU",
        "sp_api_endpoint": SP_API_ENDPOINTS["EU"],
        "currency": "EUR",
        "locale": "de-DE",
        "tld": "de",
        "country_name": "Germany",
    },
    "FR": {
        "sp_api_marketplace_id": "A13V1IB3VIYZZH",
        "keepa_domain_id": 4,
        "sp_api_region": "EU",
        "sp_api_endpoint": SP_API_ENDPOINTS["EU"],
        "currency": "EUR",
        "locale": "fr-FR",
        "tld": "fr",
        "country_name": "France",
    },
    "IT": {
        "sp_api_marketplace_id": "APJ6JRA9NG5V4",
        "keepa_domain_id": 8,
        "sp_api_region": "EU",
        "sp_api_endpoint": SP_API_ENDPOINTS["EU"],
        "currency": "EUR",
        "locale": "it-IT",
        "tld": "it",
        "country_name": "Italy",
    },
    "ES": {
        "sp_api_marketplace_id": "A1RKKUPIHCS9HS",
        "keepa_domain_id": 9,
        "sp_api_region": "EU",
        "sp_api_endpoint": SP_API_ENDPOINTS["EU"],
        "currency": "EUR",
        "locale": "es-ES",
        "tld": "es",
        "country_name": "Spain",
    },
    "NL": {
        "sp_api_marketplace_id": "A1805IZSGTT6HS",
        "keepa_domain_id": None,  # Keepa does not cover NL
        "sp_api_region": "EU",
        "sp_api_endpoint": SP_API_ENDPOINTS["EU"],
        "currency": "EUR",
        "locale": "nl-NL",
        "tld": "nl",
        "country_name": "Netherlands",
    },
    "SE": {
        "sp_api_marketplace_id": "A2NODRKZP88ZB9",
        "keepa_domain_id": None,
        "sp_api_region": "EU",
        "sp_api_endpoint": SP_API_ENDPOINTS["EU"],
        "currency": "SEK",
        "locale": "sv-SE",
        "tld": "se",
        "country_name": "Sweden",
    },
    "PL": {
        "sp_api_marketplace_id": "A1C3SOZRARQ6R3",
        "keepa_domain_id": None,
        "sp_api_region": "EU",
        "sp_api_endpoint": SP_API_ENDPOINTS["EU"],
        "currency": "PLN",
        "locale": "pl-PL",
        "tld": "pl",
        "country_name": "Poland",
    },
    "BE": {
        "sp_api_marketplace_id": "AMEN7PMS3EDWL",
        "keepa_domain_id": None,
        "sp_api_region": "EU",
        "sp_api_endpoint": SP_API_ENDPOINTS["EU"],
        "currency": "EUR",
        "locale": "nl-BE",
        "tld": "com.be",
        "country_name": "Belgium",
    },
    "IE": {
        "sp_api_marketplace_id": "A28R8C7NBKEWEA",
        "keepa_domain_id": None,
        "sp_api_region": "EU",
        "sp_api_endpoint": SP_API_ENDPOINTS["EU"],
        "currency": "EUR",
        "locale": "en-IE",
        "tld": "ie",
        "country_name": "Ireland",
    },
    "TR": {
        "sp_api_marketplace_id": "A33AVAJ2PDY3EV",
        "keepa_domain_id": None,
        "sp_api_region": "EU",
        "sp_api_endpoint": SP_API_ENDPOINTS["EU"],
        "currency": "TRY",
        "locale": "tr-TR",
        "tld": "com.tr",
        "country_name": "Turkey",
    },
    "ZA": {
        "sp_api_marketplace_id": "AE08WJ6YKNBMC",
        "keepa_domain_id": None,
        "sp_api_region": "EU",
        "sp_api_endpoint": SP_API_ENDPOINTS["EU"],
        "currency": "ZAR",
        "locale": "en-ZA",
        "tld": "co.za",
        "country_name": "South Africa",
    },
    "EG": {
        "sp_api_marketplace_id": "ARBP9OOSHTCHU",
        "keepa_domain_id": None,
        "sp_api_region": "EU",
        "sp_api_endpoint": SP_API_ENDPOINTS["EU"],
        "currency": "EGP",
        "locale": "ar-EG",
        "tld": "eg",
        "country_name": "Egypt",
    },
    "SA": {
        "sp_api_marketplace_id": "A17E79C6D8DWNP",
        "keepa_domain_id": None,
        "sp_api_region": "EU",
        "sp_api_endpoint": SP_API_ENDPOINTS["EU"],
        "currency": "SAR",
        "locale": "ar-SA",
        "tld": "sa",
        "country_name": "Saudi Arabia",
    },
    "AE": {
        "sp_api_marketplace_id": "A2VIGQ35RCS4UG",
        "keepa_domain_id": None,
        "sp_api_region": "EU",
        "sp_api_endpoint": SP_API_ENDPOINTS["EU"],
        "currency": "AED",
        "locale": "ar-AE",
        "tld": "ae",
        "country_name": "United Arab Emirates",
    },
    # Far East / Asia-Pacific
    "JP": {
        "sp_api_marketplace_id": "A1VC38T7YXB528",
        "keepa_domain_id": 5,
        "sp_api_region": "FE",
        "sp_api_endpoint": SP_API_ENDPOINTS["FE"],
        "currency": "JPY",
        "locale": "ja-JP",
        "tld": "co.jp",
        "country_name": "Japan",
    },
    "AU": {
        "sp_api_marketplace_id": "A39IBJ37TRP1C6",
        "keepa_domain_id": None,
        "sp_api_region": "FE",
        "sp_api_endpoint": SP_API_ENDPOINTS["FE"],
        "currency": "AUD",
        "locale": "en-AU",
        "tld": "com.au",
        "country_name": "Australia",
    },
    "SG": {
        "sp_api_marketplace_id": "A19VAU5U5O7RUS",
        "keepa_domain_id": None,
        "sp_api_region": "FE",
        "sp_api_endpoint": SP_API_ENDPOINTS["FE"],
        "currency": "SGD",
        "locale": "en-SG",
        "tld": "sg",
        "country_name": "Singapore",
    },
    "IN": {
        # SP-API marketplace-ids page labels India region "AP" (Asia-Pacific);
        # endpoints page only lists NA/EU/FE. We route through FE to match
        # current sp_api.py behavior. Revisit if Amazon publishes AP endpoint.
        "sp_api_marketplace_id": "A21TJRUUN4KGV",
        "keepa_domain_id": 10,
        "sp_api_region": "FE",
        "sp_api_endpoint": SP_API_ENDPOINTS["FE"],
        "currency": "INR",
        "locale": "en-IN",
        "tld": "in",
        "country_name": "India",
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_marketplace(region_code: str) -> dict[str, Any] | None:
    """Return the full metadata dict for a region, or None if unknown.

    Region codes are 2-letter ISO-3166 uppercase (e.g., "DE", "JP"). Lookup is
    case-insensitive — lowercase / mixed-case inputs are normalized.
    """
    if not region_code:
        return None
    return MARKETPLACES.get(region_code.upper())


def list_marketplaces() -> list[str]:
    """Return the list of supported region codes, sorted alphabetically."""
    return sorted(MARKETPLACES.keys())


def region_for_keepa_domain(domain_id: str | int | None) -> str | None:
    """Given a Keepa domain ID (int or numeric string), return the region code.

    Returns None for unknown or Keepa-unsupported domains. Keepa's AmazonLocale
    enum covers only 12 regions (domain IDs 1-12, with 0 and 7 reserved);
    SP-API-only regions (AU, SG, BR, NL, SE, PL, BE, TR, etc.) have no Keepa
    domain and will not match.
    """
    if domain_id is None or domain_id == "":
        return None
    try:
        target = int(domain_id)
    except (TypeError, ValueError):
        return None
    for code, data in MARKETPLACES.items():
        if data["keepa_domain_id"] == target:
            return code
    return None


def region_for_sp_api_id(marketplace_id: str) -> str | None:
    """Given an SP-API marketplace ID, return the region code. Case-sensitive."""
    if not marketplace_id:
        return None
    for code, data in MARKETPLACES.items():
        if data["sp_api_marketplace_id"] == marketplace_id:
            return code
    return None
