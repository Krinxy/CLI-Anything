"""Channels inside a guild."""

from cli_anything.discord.utils.discord_backend import DiscordClient, snowflake

# https://discord.com/developers/docs/resources/channel#channel-object-channel-types
CHANNEL_TYPES = {0: "text", 2: "voice", 4: "category", 5: "announcement", 13: "stage", 15: "forum"}


def list_channels(client: DiscordClient, guild_id: str) -> list:
    channels = client.get(f"/guilds/{snowflake(guild_id, 'guild id')}/channels")
    return [{"id": c["id"], "name": c.get("name"), "type": CHANNEL_TYPES.get(c["type"], c["type"]),
             "parent_id": c.get("parent_id")} for c in channels]


def get_channel(client: DiscordClient, channel_id: str) -> dict:
    return client.get(f"/channels/{snowflake(channel_id, 'channel id')}")
