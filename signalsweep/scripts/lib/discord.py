"""Discord server message search (signalsweep 3.23.0+).

**Envelope-first.** Discord's search API requires the bot to be a member
of the target guild AND have Read Message History permission. Signalsweep
ships this as an envelope-first adapter: `DISCORD_BOT_TOKEN` + `DISCORD_GUILD_ID`
must both be set, otherwise returns `credentials_missing`.

Endpoint: `discord.com/api/v10/guilds/{guild_id}/messages/search`.

v3.7 paid-APIs + creds.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

ENDPOINT_TEMPLATE = "https://discord.com/api/v10/guilds/{guild_id}/messages/search"


def search_discord(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    token = cfg.get("DISCORD_BOT_TOKEN")
    guild_id = cfg.get("DISCORD_GUILD_ID")
    if not token or not guild_id:
        return {"items": None, "error": "credentials_missing"}
    url = ENDPOINT_TEMPLATE.format(guild_id=guild_id)
    params = {"content": topic}
    return paid_api.fetch_json(
        url,
        params=params,
        extra_headers={"Authorization": f"Bot {token}"},
    )


def parse_discord_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    messages = response["items"].get("messages") or []
    out = []
    # Discord nests messages in [[msg, ...], [msg, ...]] groups for context
    for group in messages:
        if not isinstance(group, list) or not group:
            continue
        msg = group[0]
        mid = msg.get("id")
        if not mid:
            continue
        author = msg.get("author") or {}
        out.append({
            "id": f"discord:{mid}",
            "title": f"#{msg.get('channel_id', '?')} · @{author.get('username', '?')}",
            "snippet": (msg.get("content") or "")[:500],
            "url": f"https://discord.com/channels/{msg.get('guild_id', '')}/{msg.get('channel_id', '')}/{mid}",
            "source_domain": "discord.com",
            "date": (msg.get("timestamp") or "")[:10],
            "author": author.get("username"),
            "relevance": 0.65,
            "why_relevant": f"Discord message by @{author.get('username', '?')}",
            "metadata": {
                "platform": "discord",
                "message_id": mid,
                "channel_id": msg.get("channel_id"),
                "guild_id": msg.get("guild_id"),
                "author_id": author.get("id"),
            },
        })
    return out
