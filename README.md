# SignalSweep Open

Public, cost-safe distribution package for SignalSweep.

SignalSweep is an agentic research skill that searches many public, local, and bring-your-own-key sources in one sweep. This repository contains the public `.skill` package contents only. It does not include private operator automation, browser-cookie helper scripts, local store/watchlist/briefing tools, tests, fixtures, hooks, or any shared credentials.

## Download

Latest public package:

```text
https://github.com/tripleyak/signalsweep-open/releases/download/v3.28.3/signalsweep-open.skill
```

SHA256:

```text
15a066b1b38b8f7bbc516c40a85540a5ed8f6fa2b089efc5f2cf90dcca720524
```

Verify after download:

```bash
shasum -a 256 signalsweep-open.skill
```

## Install

Upload `signalsweep-open.skill` to any skill host that supports `.skill` packages, then run `/signalsweep`.

The extracted source used to build the package lives in [`signalsweep/`](signalsweep/).

### Claude Code / Codex Workshop Install

For a local workshop install on macOS:

```bash
set -e
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
HOMEBREW_NO_AUTO_UPDATE=1 brew install python@3.12
mkdir -p ~/.claude/skills ~/.codex/skills
curl -L --fail -o /tmp/signalsweep-open.skill \
  https://github.com/tripleyak/signalsweep-open/releases/download/v3.28.3/signalsweep-open.skill
shasum -a 256 /tmp/signalsweep-open.skill
unzip -q -o /tmp/signalsweep-open.skill -d ~/.claude/skills
unzip -q -o /tmp/signalsweep-open.skill -d ~/.codex/skills
SIGNALSWEEP_PYTHON="$(command -v python3.13 || command -v python3.12 || command -v python3)"
"$SIGNALSWEEP_PYTHON" - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit("SignalSweep needs Python 3.12+. Run: brew install python@3.12")
print(f"Using Python {sys.version.split()[0]}")
PY
"$SIGNALSWEEP_PYTHON" ~/.claude/skills/signalsweep/scripts/signalsweep.py setup --free-public-keys --write-template
```

Restart Claude Code or Codex after install, then run:

```text
/signalsweep pickleball paddle grip sweaty hands
```

Expected checksum:

```text
15a066b1b38b8f7bbc516c40a85540a5ed8f6fa2b089efc5f2cf90dcca720524
```

## Public Safety Defaults

The package embeds `public-profile: true` and starts in a cost-safe mode:

- no bundled secrets, cookies, shared API keys, or shared proxy accounts
- paid/API-backed tiers disabled unless you set `SIGNALSWEEP_DISABLE_PAID_APIS=0`
- Deep Research disabled and capped at `0` unless you opt in
- browser cookie extraction off by default with `FROM_BROWSER=off`
- local SQLite store, watchlist, briefing, and browser-cookie helper scripts excluded

Free/no-auth sources work by default. Optional local CLIs like `gh` and `yt-dlp` can unlock GitHub and YouTube from your own machine without sharing credentials.

## Workshop Free Key Setup

Workshop attendees can add their own free public API keys after install:

```bash
cd signalsweep
python3 scripts/signalsweep.py setup --free-public-keys --write-template
```

This writes a commented template to `~/.config/signalsweep/.env` without overwriting existing values. Users paste their own keys there when ready; this package does not include shared keys.

The template covers:

- `BEA_API_KEY`
- `USDA_NASS_API_KEY`
- `USDA_FOODDATA_API_KEY`
- `OPENFDA_API_KEY`
- `YOUTUBE_API_KEY`
- `SEMANTIC_SCHOLAR_API_KEY`
- `NCBI_API_KEY`
- `CDC_APP_TOKEN`
- `SEC_EDGAR_CONTACT_EMAIL`
- `OPENALEX_CONTACT_EMAIL`

## Opt Into Paid Or Private Sources

Add your own keys locally if you want the paid or account-backed tiers:

```bash
SIGNALSWEEP_DISABLE_PAID_APIS=0
SIGNALSWEEP_DISABLE_DEEP_RESEARCH=0
SIGNALSWEEP_DEEP_RESEARCH_MAX_COST=10
FROM_BROWSER=auto
```

Keep credentials in your own environment or local `.env`; do not commit them.

## What Is Excluded

This public distribution intentionally excludes:

- private repo history
- private tests, fixtures, hooks, and planning docs
- local automation scripts for store/watchlist/briefing
- browser-cookie extraction helpers
- any shared API keys, cookies, tokens, or OAuth credentials

For license terms, see [`LICENSE`](LICENSE).
