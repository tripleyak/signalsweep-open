"""Environment and API key management for signalsweep skill."""

from __future__ import annotations

import base64
import binascii
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

# Allow override via environment variable for testing
# Set LAST30DAYS_CONFIG_DIR="" for clean/no-config mode
# Set LAST30DAYS_CONFIG_DIR="/path/to/dir" for custom config location
if 'SIGNALSWEEP_CONFIG_DIR' in os.environ:
    _config_override = os.environ.get('SIGNALSWEEP_CONFIG_DIR')
else:
    _config_override = os.environ.get('LAST30DAYS_CONFIG_DIR')
if _config_override == "":
    # Empty string = no config file (clean mode)
    CONFIG_DIR = None
    CONFIG_FILE = None
elif _config_override:
    CONFIG_DIR = Path(_config_override)
    CONFIG_FILE = CONFIG_DIR / ".env"
else:
    # Default: prefer signalsweep's own config, fall back to upstream last30days for migration.
    _signalsweep_dir = Path.home() / ".config" / "signalsweep"
    _last30days_dir = Path.home() / ".config" / "last30days"
    if (_signalsweep_dir / ".env").exists():
        CONFIG_DIR = _signalsweep_dir
    elif (_last30days_dir / ".env").exists():
        CONFIG_DIR = _last30days_dir
    else:
        CONFIG_DIR = _signalsweep_dir  # signalsweep is canonical; setup wizard will create it
    CONFIG_FILE = CONFIG_DIR / ".env"

CODEX_AUTH_FILE = Path(os.environ.get("CODEX_AUTH_FILE", str(Path.home() / ".codex" / "auth.json")))

# macOS Keychain integration: items stored with this service prefix are picked
# up automatically on Darwin as the lowest-priority credential source.
KEYCHAIN_SERVICE_PREFIX = "signalsweep-"

KEYCHAIN_KEYS = (
    "OPENAI_API_KEY", "XAI_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY",
    "GOOGLE_GENAI_API_KEY", "ANTHROPIC_API_KEY", "SCRAPECREATORS_API_KEY",
    "APIFY_API_TOKEN", "AUTH_TOKEN", "CT0", "BSKY_HANDLE", "BSKY_APP_PASSWORD",
    "TRUTHSOCIAL_TOKEN", "BRAVE_API_KEY", "EXA_API_KEY", "SERPER_API_KEY",
    "OPENROUTER_API_KEY", "PARALLEL_API_KEY", "XQUIK_API_KEY",
    "XIAOHONGSHU_API_BASE",
    # v3.28 session additions — Keychain fallback for keys that survive .env wipes
    "FRED_API_KEY", "NEWSAPI_KEY", "YELP_API_KEY", "YOUTUBE_API_KEY",
    "TADDY_USER_ID", "TADDY_API_KEY", "ETSY_API_KEY", "FINNHUB_API_KEY",
    "ALPHAVANTAGE_API_KEY", "POLYGON_API_KEY", "OPENWEATHER_API_KEY",
    "PRODUCTHUNT_TOKEN", "COURTLISTENER_API_TOKEN", "PATENTSVIEW_API_KEY",
    "EPA_AIRNOW_API_KEY", "NOAA_CDO_TOKEN", "ETHERSCAN_API_KEY",
    "GOOGLE_PLACES_API_KEY", "SERPAPI_API_KEY", "LISTENNOTES_API_KEY",
)


def is_public_package() -> bool:
    """Return True when running from a public-profile skill package."""
    skill_root = Path(__file__).resolve().parents[2]
    if (skill_root / ".signalsweep-public").exists():
        return True
    skill_md = skill_root / "SKILL.md"
    try:
        return "public-profile: true" in skill_md.read_text(encoding="utf-8")
    except OSError:
        return False

AuthSource = Literal["api_key", "codex", "none"]
AuthStatus = Literal["ok", "missing", "expired", "missing_account_id"]

AUTH_SOURCE_API_KEY: AuthSource = "api_key"
AUTH_SOURCE_CODEX: AuthSource = "codex"
AUTH_SOURCE_NONE: AuthSource = "none"

AUTH_STATUS_OK: AuthStatus = "ok"
AUTH_STATUS_MISSING: AuthStatus = "missing"
AUTH_STATUS_EXPIRED: AuthStatus = "expired"
AUTH_STATUS_MISSING_ACCOUNT_ID: AuthStatus = "missing_account_id"


@dataclass(frozen=True)
class OpenAIAuth:
    token: str | None
    source: AuthSource
    status: AuthStatus
    account_id: str | None
    codex_auth_file: str


def _check_file_permissions(path: Path) -> None:
    """Warn to stderr if a secrets file has overly permissive permissions."""
    if os.name == "nt":
        return

    try:
        mode = path.stat().st_mode
        # Check if group or other can read (bits 0o044)
        if mode & 0o044:
            sys.stderr.write(
                f"[signalsweep] WARNING: {path} is readable by other users. "
                f"Run: chmod 600 {path}\n"
            )
            sys.stderr.flush()
    except OSError as exc:
        sys.stderr.write(f"[signalsweep] WARNING: could not stat {path}: {exc}\n")
        sys.stderr.flush()


def load_env_file(path: Path) -> dict[str, str]:
    """Load environment variables from a file."""
    env = {}
    if not path or not path.exists():
        return env
    _check_file_permissions(path)

    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip()
                # Remove quotes if present
                if value and value[0] in ('"', "'") and value[-1] == value[0]:
                    value = value[1:-1]
                if key and value:
                    env[key] = value
    return env


def _load_keychain(keys: list[str]) -> dict[str, str]:
    """Load credentials from macOS Keychain as lowest-priority config."""
    import platform
    if platform.system() != "Darwin":
        return {}

    import shutil
    security = shutil.which("security")
    if not security:
        return {}

    import pwd
    import subprocess
    user = os.environ.get("USER") or pwd.getpwuid(os.getuid()).pw_name
    env: dict[str, str] = {}
    for key in keys:
        for service_prefix in (KEYCHAIN_SERVICE_PREFIX, "last30days-"):
            try:
                proc = subprocess.run(
                    [
                        security,
                        "find-generic-password",
                        "-a",
                        user,
                        "-s",
                        f"{service_prefix}{key}",
                        "-w",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if proc.returncode == 0 and proc.stdout.strip():
                env[key] = proc.stdout.strip()
                break
    return env


def _decode_jwt_payload(token: str) -> dict[str, Any] | None:
    """Decode JWT payload without verification."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1]
        pad = "=" * (-len(payload_b64) % 4)
        decoded = base64.urlsafe_b64decode(payload_b64 + pad)
        return json.loads(decoded.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, binascii.Error, IndexError) as exc:
        sys.stderr.write(f"[signalsweep] WARNING: malformed JWT token: {exc}\n")
        sys.stderr.flush()
        return None


def _token_expired(token: str, leeway_seconds: int = 60) -> bool:
    """Check if JWT token is expired."""
    payload = _decode_jwt_payload(token)
    if not payload:
        return False
    exp = payload.get("exp")
    if not exp:
        return False
    return exp <= (time.time() + leeway_seconds)


def extract_chatgpt_account_id(access_token: str) -> str | None:
    """Extract chatgpt_account_id from JWT token."""
    payload = _decode_jwt_payload(access_token)
    if not payload:
        return None
    auth_claim = payload.get("https://api.openai.com/auth", {})
    if isinstance(auth_claim, dict):
        return auth_claim.get("chatgpt_account_id")
    return None


def load_codex_auth(path: Path = CODEX_AUTH_FILE) -> dict[str, Any]:
    """Load Codex auth JSON."""
    if not path.exists():
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        sys.stderr.write(
            f"[signalsweep] WARNING: {path} exists but contains invalid JSON -- ignoring\n"
        )
        sys.stderr.flush()
        return {}


def get_codex_access_token() -> tuple[str | None, str]:
    """Get Codex access token from auth.json.

    Returns:
        (token, status) where status is 'ok', 'missing', or 'expired'
    """
    auth = load_codex_auth()
    token = None
    if isinstance(auth, dict):
        tokens = auth.get("tokens") or {}
        if isinstance(tokens, dict):
            token = tokens.get("access_token")
        if not token:
            token = auth.get("access_token")
    if not token:
        return None, AUTH_STATUS_MISSING
    if _token_expired(token):
        return None, AUTH_STATUS_EXPIRED
    return token, AUTH_STATUS_OK


def get_openai_auth(file_env: dict[str, str]) -> OpenAIAuth:
    """Resolve OpenAI auth from API key or Codex login."""
    api_key = os.environ.get('OPENAI_API_KEY') or file_env.get('OPENAI_API_KEY')
    if api_key:
        return OpenAIAuth(
            token=api_key,
            source=AUTH_SOURCE_API_KEY,
            status=AUTH_STATUS_OK,
            account_id=None,
            codex_auth_file=str(CODEX_AUTH_FILE),
        )

    # Codex auth (chatgpt.com backend) intentionally skipped.
    # The endpoint is unstable and causes crashes when the token expires.
    # Users who want OpenAI should set OPENAI_API_KEY explicitly.

    return OpenAIAuth(
        token=None,
        source=AUTH_SOURCE_NONE,
        status=AUTH_STATUS_MISSING,
        account_id=None,
        codex_auth_file=str(CODEX_AUTH_FILE),
    )


def _find_project_env() -> Path | None:
    """Find per-project .env by walking up from cwd.

    Searches for .claude/signalsweep.env, then .claude/last30days.env, in each parent directory,
    stopping at the user's home directory or filesystem root.
    """
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        for filename in ('signalsweep.env', 'last30days.env'):
            candidate = parent / '.claude' / filename
            if candidate.exists():
                return candidate
        # Stop at filesystem root or home
        if parent == Path.home() or parent == parent.parent:
            break
    return None


def get_config() -> dict[str, Any]:
    """Load configuration from multiple sources.

    Priority (highest wins):
      1. Environment variables (os.environ)
      2. .claude/signalsweep.env or .claude/last30days.env (per-project config)
      3. ~/.config/signalsweep/.env (global config)
    """
    # Load from global config file
    file_env = load_env_file(CONFIG_FILE) if CONFIG_FILE else {}

    # Load from per-project config (overrides global)
    project_env_path = _find_project_env()
    project_env = load_env_file(project_env_path) if project_env_path else {}

    # Merge: project overrides global
    merged_env = {**file_env, **project_env}

    # Keychain is the lowest-priority source (Darwin only; no-op elsewhere).
    # Loaded before openai_auth so OPENAI_API_KEY can come from Keychain too.
    keychain_env = _load_keychain(list(KEYCHAIN_KEYS))
    merged_env = {**keychain_env, **merged_env}

    openai_auth = get_openai_auth(merged_env)

    # Build config: Codex/OpenAI auth + process.env > project .env > global .env
    config = {
        'OPENAI_API_KEY': openai_auth.token,
        'OPENAI_AUTH_SOURCE': openai_auth.source,
        'OPENAI_AUTH_STATUS': openai_auth.status,
        'OPENAI_CHATGPT_ACCOUNT_ID': openai_auth.account_id,
        'CODEX_AUTH_FILE': openai_auth.codex_auth_file,
    }

    keys = [
        ('XAI_API_KEY', None),
        ('GOOGLE_API_KEY', None),
        ('GEMINI_API_KEY', None),
        ('GOOGLE_GENAI_API_KEY', None),
        ('XIAOHONGSHU_API_BASE', None),
        ('SIGNALSWEEP_REASONING_PROVIDER', None),
        ('SIGNALSWEEP_MODEL_PIN', None),
        ('SIGNALSWEEP_PLANNER_MODEL', None),
        ('SIGNALSWEEP_RERANK_MODEL', None),
        ('SIGNALSWEEP_X_MODEL', None),
        ('SIGNALSWEEP_X_BACKEND', None),
        ('SIGNALSWEEP_AUTO_PROVIDER_ORDER', None),
        ('LAST30DAYS_REASONING_PROVIDER', 'auto'),
        ('LAST30DAYS_PLANNER_MODEL', None),
        ('LAST30DAYS_RERANK_MODEL', None),
        ('LAST30DAYS_X_MODEL', None),
        ('LAST30DAYS_X_BACKEND', None),
        ('LAST30DAYS_STORE', None),
        ('OPENAI_MODEL_PIN', None),
        ('ANTHROPIC_MODEL_PIN', None),
        ('GEMINI_MODEL_PIN', None),
        ('OPENROUTER_MODEL_PIN', None),
        ('XAI_MODEL_PIN', None),
        ('SCRAPECREATORS_API_KEY', None),
        ('APIFY_API_TOKEN', None),
        ('AUTH_TOKEN', None),
        ('CT0', None),
        ('BSKY_HANDLE', None),
        ('BSKY_APP_PASSWORD', None),
        ('BSKY_SEARCH_HOST', None),
        ('TRUTHSOCIAL_TOKEN', None),
        ('BRAVE_API_KEY', None),
        ('EXA_API_KEY', None),
        ('SERPER_API_KEY', None),
        ('OPENROUTER_API_KEY', None),
        ('PARALLEL_API_KEY', None),
        ('XQUIK_API_KEY', None),
        ('FROM_BROWSER', None),
        ('SETUP_COMPLETE', None),
        ('INCLUDE_SOURCES', ''),
        ('EXCLUDE_SOURCES', ''),
        ('LAST30DAYS_YOUTUBE_SSH_HOST', None),
        ('LAST30DAYS_TRANSCRIPT_TIMEOUT', None),
        ('SIGNALSWEEP_PUBLIC_MODE', "1" if is_public_package() else None),
        # v3.6 public-data toggle
        ('SIGNALSWEEP_DISABLE_PUBLIC_APIS', None),
        # v3.7 paid-API tier
        ('SIGNALSWEEP_DISABLE_PAID_APIS', None),
        ('KEEPA_API_KEY', None),
        ('KEEPA_DOMAIN_ID', None),
        ('KEEPA_MAX_CALLS', None),
        ('HELIUM10_API_KEY', None),
        ('JUNGLESCOUT_API_KEY', None),
        ('DATADIVE_API_KEY', None),
        ('SMARTSCOUT_API_KEY', None),
        ('SERPAPI_API_KEY', None),
        # Amazon LWA OAuth (shared by SP-API + Ads API)
        ('AMAZON_LWA_CLIENT_ID', None),
        ('AMAZON_LWA_CLIENT_SECRET', None),
        ('AMAZON_LWA_REFRESH_TOKEN', None),
        # SP-API
        ('AMAZON_SP_API_REGION', None),
        ('AMAZON_SELLER_ID', None),
        ('AMAZON_SP_API_PROFILES', None),
        ('AMAZON_SP_API_ACTIVE_PROFILE', None),
        # Ads API
        ('AMAZON_ADS_PROFILE_ID', None),
        ('AMAZON_ADS_PROFILES', None),
        ('AMAZON_ADS_ACTIVE_PROFILE', None),
        # v3.27.0 Shopify "bring your own store"
        ('SHOPIFY_STORE', None),
        ('SHOPIFY_ACCESS_TOKEN', None),
        # v3.8 deep-research tier
        ('SIGNALSWEEP_DISABLE_DEEP_RESEARCH', None),
        ('SIGNALSWEEP_DEEP_RESEARCH_MAX_COST', None),
        ('ANTHROPIC_API_KEY', None),
        ('OPENROUTER_RESEARCH_MODEL', None),
    ]

    for key, default in keys:
        config[key] = os.environ.get(key) or merged_env.get(key, default)

    if _truthy(config.get("SIGNALSWEEP_PUBLIC_MODE")):
        if "SIGNALSWEEP_DISABLE_PAID_APIS" not in os.environ and "SIGNALSWEEP_DISABLE_PAID_APIS" not in merged_env:
            config["SIGNALSWEEP_DISABLE_PAID_APIS"] = "1"
        if "SIGNALSWEEP_DISABLE_DEEP_RESEARCH" not in os.environ and "SIGNALSWEEP_DISABLE_DEEP_RESEARCH" not in merged_env:
            config["SIGNALSWEEP_DISABLE_DEEP_RESEARCH"] = "1"
        if "SIGNALSWEEP_DEEP_RESEARCH_MAX_COST" not in os.environ and "SIGNALSWEEP_DEEP_RESEARCH_MAX_COST" not in merged_env:
            config["SIGNALSWEEP_DEEP_RESEARCH_MAX_COST"] = "0"
        if "FROM_BROWSER" not in os.environ and "FROM_BROWSER" not in merged_env:
            config["FROM_BROWSER"] = "off"
        if "LAST30DAYS_STORE" not in os.environ and "LAST30DAYS_STORE" not in merged_env:
            config["LAST30DAYS_STORE"] = "0"

    # SignalSweep is the canonical user-facing namespace. Keep upstream
    # LAST30DAYS_* compatibility by mirroring modern aliases into the legacy
    # keys the older planner/provider code still reads.
    alias_pairs = (
        ("SIGNALSWEEP_REASONING_PROVIDER", "LAST30DAYS_REASONING_PROVIDER", "auto"),
        ("SIGNALSWEEP_PLANNER_MODEL", "LAST30DAYS_PLANNER_MODEL", None),
        ("SIGNALSWEEP_RERANK_MODEL", "LAST30DAYS_RERANK_MODEL", None),
        ("SIGNALSWEEP_X_MODEL", "LAST30DAYS_X_MODEL", None),
        ("SIGNALSWEEP_X_BACKEND", "LAST30DAYS_X_BACKEND", None),
    )
    for modern_key, legacy_key, default in alias_pairs:
        modern_value = os.environ.get(modern_key) or merged_env.get(modern_key)
        legacy_value = os.environ.get(legacy_key) or merged_env.get(legacy_key)
        chosen = modern_value or legacy_value or default
        config[modern_key] = chosen
        config[legacy_key] = chosen

    # Backward-compat: ScrapeCreators examples often use the vendor spelling.
    if not config.get('SCRAPECREATORS_API_KEY'):
        legacy = os.environ.get('SCRAPE_CREATORS_API_KEY') or merged_env.get('SCRAPE_CREATORS_API_KEY')
        if legacy:
            config['SCRAPECREATORS_API_KEY'] = legacy

    sc_key_raw = config.get('SCRAPECREATORS_API_KEY') or ''
    if ',' in sc_key_raw:
        import random
        sc_keys = [k.strip() for k in sc_key_raw.split(',') if k.strip()]
        config['SCRAPECREATORS_API_KEY'] = random.choice(sc_keys) if sc_keys else ''

    # Pass through ALL remaining .env keys not already in config.
    # This ensures new source credentials (v3.9+) are available without
    # needing to manually add each key to the whitelist above.
    for key, value in merged_env.items():
        if key not in config:
            config[key] = os.environ.get(key) or value

    # Track which config source was used
    if project_env_path:
        config['_CONFIG_SOURCE'] = f'project:{project_env_path}'
    elif CONFIG_FILE and CONFIG_FILE.exists():
        config['_CONFIG_SOURCE'] = f'global:{CONFIG_FILE}'
    elif keychain_env:
        config['_CONFIG_SOURCE'] = 'keychain'
    else:
        config['_CONFIG_SOURCE'] = 'env_only'

    # Extract browser credentials if configured
    browser_creds = extract_browser_credentials(config)
    for key, value in browser_creds.items():
        if not config.get(key):
            config[key] = value
            config[f"_{key}_SOURCE"] = "browser"

    return config


# ---------------------------------------------------------------------------
# Browser cookie extraction
# ---------------------------------------------------------------------------

COOKIE_DOMAINS: dict[str, dict[str, Any]] = {
    "x": {
        "domain": ".x.com",
        "cookies": ["auth_token", "ct0"],
        "mapping": {"auth_token": "AUTH_TOKEN", "ct0": "CT0"},
    },
    "truthsocial": {
        "domain": ".truthsocial.com",
        "cookies": ["_session_id"],
        "mapping": {"_session_id": "TRUTHSOCIAL_TOKEN"},
    },
}


def extract_browser_credentials(config: dict[str, Any]) -> dict[str, str]:
    """Extract auth cookies from local browsers.

    Default behavior (FROM_BROWSER unset): tries Firefox and Safari only.
    These read local files silently with no system dialogs.  Chrome is
    skipped because ``security find-generic-password`` triggers a macOS
    Keychain prompt that cannot be reliably suppressed.

    Set ``FROM_BROWSER=auto`` to also try Chrome (accepts the dialog),
    or ``FROM_BROWSER=off`` to disable extraction entirely.
    """
    from_browser = (config.get("FROM_BROWSER") or "").strip().lower()
    if from_browser == "off":
        return {}
    try:
        from . import cookie_extract
    except ImportError:
        return {}
    # Determine which browsers to try
    if from_browser in ("firefox", "chrome", "safari"):
        browsers = [from_browser]
    elif from_browser == "auto":
        browsers = ["firefox", "safari", "chrome"]
    else:
        # Default: silent browsers only (no Keychain dialog)
        browsers = ["firefox", "safari"]
    extracted: dict[str, str] = {}
    for _service, spec in COOKIE_DOMAINS.items():
        if all(config.get(env_key) for env_key in spec["mapping"].values()):
            continue
        for browser in browsers:
            try:
                cookies = cookie_extract.extract_cookies(browser, spec["domain"], spec["cookies"])
            except Exception:
                continue
            if cookies:
                for cookie_name, env_key in spec["mapping"].items():
                    if cookie_name in cookies and not config.get(env_key):
                        extracted[env_key] = cookies[cookie_name]
                break  # Found cookies for this service, stop trying browsers
    return extracted


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def get_x_source_with_method(config: dict[str, Any]) -> tuple[str | None, str]:
    """Return (source, method) for X search, where method describes the auth origin."""
    if config.get("XAI_API_KEY"):
        return "xai", "xai"
    if config.get("AUTH_TOKEN") and config.get("CT0"):
        method = config.get("_AUTH_TOKEN_SOURCE", "env")
        return "bird", method
    from . import xurl_x
    if xurl_x.is_available():
        return "xurl", "xurl"
    return None, "none"


def config_exists() -> bool:
    """Check if any configuration source exists."""
    if _find_project_env():
        return True
    if CONFIG_FILE:
        return CONFIG_FILE.exists()
    return False


def is_reddit_available(config: dict[str, Any]) -> bool:
    """Check if Reddit search is available.

    v3 uses ScrapeCreators only.
    """
    return bool(config.get('SCRAPECREATORS_API_KEY'))


def get_reddit_source(config: dict[str, Any]) -> str | None:
    """Determine which Reddit backend to use.

    Returns: 'scrapecreators' or None
    """
    if config.get('SCRAPECREATORS_API_KEY'):
        return 'scrapecreators'
    return None


def get_x_source(config: dict[str, Any]) -> str | None:
    """Determine the best available explicit X/Twitter source.

    Priority: explicit backend pin, then xAI, then Bird with explicit cookies,
    then xurl CLI.

    Browser-cookie probing is intentionally not used here. Automatic Keychain
    access causes popups during normal pipeline runs. Bird is only considered
    available when AUTH_TOKEN and CT0 are present explicitly.

    Args:
        config: Configuration dict from get_config()

    Returns:
        'bird' if Bird is installed and explicit cookies are configured,
        'xai' if XAI_API_KEY is configured,
        'xurl' if xurl CLI is installed and authenticated,
        None if no X source available.
    """
    from . import bird_x, xurl_x

    preferred = (config.get('LAST30DAYS_X_BACKEND') or '').lower()
    has_bird_creds = bool(config.get('AUTH_TOKEN') and config.get('CT0'))
    if has_bird_creds:
        bird_x.set_credentials(config.get('AUTH_TOKEN'), config.get('CT0'))

    if preferred == 'xai':
        return 'xai' if config.get('XAI_API_KEY') else None
    if preferred == 'bird':
        return 'bird' if has_bird_creds and bird_x.is_bird_installed() else None
    if preferred == 'xurl':
        return 'xurl' if xurl_x.is_available() else None

    if config.get('XAI_API_KEY'):
        return 'xai'
    if has_bird_creds and bird_x.is_bird_installed():
        return 'bird'
    if xurl_x.is_available():
        return 'xurl'

    return None


def is_ytdlp_available() -> bool:
    """Check if yt-dlp is installed for YouTube search."""
    from . import youtube_yt
    return youtube_yt.is_ytdlp_installed()


def is_youtube_comments_available(config: dict[str, Any]) -> bool:
    """Check if YouTube comment enrichment is available.

    Requires SCRAPECREATORS_API_KEY AND youtube_comments in INCLUDE_SOURCES.
    """
    if not config.get('SCRAPECREATORS_API_KEY'):
        return False
    include = _parse_include_sources(config)
    return 'youtube_comments' in include


def is_tiktok_comments_available(config: dict[str, Any]) -> bool:
    """Check if TikTok comment enrichment is available."""
    if not config.get('SCRAPECREATORS_API_KEY'):
        return False
    include = _parse_include_sources(config)
    return 'tiktok_comments' in include


def is_youtube_sc_available(config: dict[str, Any]) -> bool:
    """Check if ScrapeCreators YouTube search fallback is available.

    Used when yt-dlp is not installed or fails.
    """
    return bool(config.get('SCRAPECREATORS_API_KEY'))


def is_hackernews_available() -> bool:
    """Check if Hacker News source is available.

    Always returns True - HN uses free Algolia API, no key needed.
    """
    return True


def is_bluesky_available(config: dict[str, Any]) -> bool:
    """Check if Bluesky source is available.

    Requires BSKY_HANDLE and BSKY_APP_PASSWORD (app password from bsky.app/settings).
    """
    return bool(config.get('BSKY_HANDLE') and config.get('BSKY_APP_PASSWORD'))


def is_truthsocial_available(config: dict[str, Any]) -> bool:
    """Check if Truth Social source is available.

    Requires TRUTHSOCIAL_TOKEN (bearer token from browser dev tools).
    """
    return bool(config.get('TRUTHSOCIAL_TOKEN'))


def is_polymarket_available() -> bool:
    """Check if Polymarket source is available.

    Always returns True - Gamma API is free, no key needed.
    """
    return True


def is_tiktok_available(config: dict[str, Any]) -> bool:
    """Check if TikTok source is available (ScrapeCreators or legacy Apify).

    Returns True if SCRAPECREATORS_API_KEY or APIFY_API_TOKEN is set.
    """
    return bool(config.get('SCRAPECREATORS_API_KEY') or config.get('APIFY_API_TOKEN'))


def get_tiktok_token(config: dict[str, Any]) -> str:
    """Get TikTok API token, preferring ScrapeCreators over legacy Apify."""
    return config.get('SCRAPECREATORS_API_KEY') or config.get('APIFY_API_TOKEN') or ''


def _parse_include_sources(config: dict[str, Any]) -> set[str]:
    """Parse INCLUDE_SOURCES config value into a set of lowercase source names."""
    raw = config.get('INCLUDE_SOURCES') or ''
    return {s.strip().lower() for s in raw.split(',') if s.strip()}


def is_threads_available(config: dict[str, Any]) -> bool:
    """Check if Threads source is available.

    Requires SCRAPECREATORS_API_KEY AND 'threads' in INCLUDE_SOURCES.
    Threads is an opt-in source - it is not activated by default.
    """
    if not config.get('SCRAPECREATORS_API_KEY'):
        return False
    return 'threads' in _parse_include_sources(config)


def is_instagram_available(config: dict[str, Any]) -> bool:
    """Check if Instagram source is available (ScrapeCreators).

    Returns True if SCRAPECREATORS_API_KEY is set.
    Instagram uses the same key as TikTok.
    """
    return bool(config.get('SCRAPECREATORS_API_KEY'))


def get_instagram_token(config: dict[str, Any]) -> str:
    """Get Instagram API token (same ScrapeCreators key as TikTok)."""
    return config.get('SCRAPECREATORS_API_KEY') or ''


def get_xiaohongshu_api_base(config: dict[str, Any]) -> str:
    """Get Xiaohongshu HTTP API base URL.

    Defaults to host.docker.internal so OpenClaw Docker can reach host service.
    """
    return (config.get('XIAOHONGSHU_API_BASE') or "http://host.docker.internal:18060").rstrip("/")


def is_xiaohongshu_available(config: dict[str, Any]) -> bool:
    """Check whether Xiaohongshu HTTP API is reachable and logged in."""
    # Import here to avoid heavy imports at module load.
    from . import http

    base = get_xiaohongshu_api_base(config)
    try:
        # Keep health probe snappy, but allow one retry for transient hiccups.
        health = http.get(f"{base}/health", timeout=3, retries=2)
        if not isinstance(health, dict):
            return False
        if not health.get("success"):
            return False

        # Login probe can be slower on some deployments (browser/session checks),
        # so use a slightly longer timeout to avoid false negatives.
        login = http.get(f"{base}/api/v1/login/status", timeout=8, retries=2)
        is_logged_in = (
            login.get("data", {}).get("is_logged_in")
            if isinstance(login, dict) else False
        )
        return bool(is_logged_in)
    except (OSError, http.HTTPError):
        return False
    except Exception as exc:
        sys.stderr.write(
            f"[signalsweep] WARNING: unexpected error checking Xiaohongshu: "
            f"{type(exc).__name__}: {exc}\n"
        )
        sys.stderr.flush()
        return False


# Backward compat alias
is_apify_available = is_tiktok_available


def get_x_source_status(config: dict[str, Any]) -> dict[str, Any]:
    """Get detailed X source status for UI decisions.

    Returns:
        Dict with keys: source, bird_installed, bird_authenticated,
        bird_username, xai_available, xurl_available, can_install_bird
    """
    from . import bird_x, xurl_x

    bird_status = bird_x.get_bird_status()
    xai_available = bool(config.get('XAI_API_KEY'))
    xurl_available = xurl_x.is_available()

    if bird_status["authenticated"]:
        source = 'bird'
    elif xai_available:
        source = 'xai'
    elif xurl_available:
        source = 'xurl'
    else:
        source = None

    return {
        "source": source,
        "bird_installed": bird_status["installed"],
        "bird_authenticated": bird_status["authenticated"],
        "bird_username": bird_status["username"],
        "xai_available": xai_available,
        "xurl_available": xurl_available,
        "can_install_bird": bird_status["can_install"],
    }


# Pinterest
def is_pinterest_available(config: dict[str, Any]) -> bool:
    """Check if Pinterest source is available.

    Returns True when SCRAPECREATORS_API_KEY is set AND 'pinterest' is in
    INCLUDE_SOURCES (or requested_sources at the pipeline level).  Pinterest
    is opt-in because not every topic benefits from visual pin results.
    """
    return bool(config.get('SCRAPECREATORS_API_KEY'))


def get_pinterest_token(config: dict[str, Any]) -> str:
    """Get Pinterest API token (same ScrapeCreators key as TikTok/Instagram)."""
    return config.get('SCRAPECREATORS_API_KEY') or ''


# Xquik
def is_xquik_available(config: dict[str, Any]) -> bool:
    """Check if Xquik X search source is available.

    Requires XQUIK_API_KEY (API key from xquik.com).
    """
    return bool(config.get('XQUIK_API_KEY'))


def get_xquik_token(config: dict[str, Any]) -> str:
    """Get Xquik API key."""
    return config.get('XQUIK_API_KEY') or ''
