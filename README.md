# SignalSweep Open

Public, cost-safe distribution package for SignalSweep.

SignalSweep is an agentic research skill that searches many public, local, and bring-your-own-key sources in one sweep. This repository contains the public `.skill` package contents only. It does not include private operator automation, browser-cookie helper scripts, local store/watchlist/briefing tools, tests, fixtures, hooks, or any shared credentials.

## Download

Latest public package:

```text
https://github.com/tripleyak/signalsweep-open/releases/download/v3.28.2/signalsweep-open.skill
```

SHA256:

```text
b01f97789f81d414271f4da1beeb459267caeade1a1ac9de9ea15a8205e6aa63
```

Verify after download:

```bash
shasum -a 256 signalsweep-open.skill
```

## Install

Upload `signalsweep-open.skill` to any skill host that supports `.skill` packages, then run `/signalsweep`.

The extracted source used to build the package lives in [`signalsweep/`](signalsweep/).

## Public Safety Defaults

The package embeds `public-profile: true` and starts in a cost-safe mode:

- no bundled secrets, cookies, shared API keys, or shared proxy accounts
- paid/API-backed tiers disabled unless you set `SIGNALSWEEP_DISABLE_PAID_APIS=0`
- Deep Research disabled and capped at `0` unless you opt in
- browser cookie extraction off by default with `FROM_BROWSER=off`
- local SQLite store, watchlist, briefing, and browser-cookie helper scripts excluded

Free/no-auth sources work by default. Optional local CLIs like `gh` and `yt-dlp` can unlock GitHub and YouTube from your own machine without sharing credentials.

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
