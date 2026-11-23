"""Guilds (servers) the bot is a member of."""

from cli_anything.discord.utils.discord_backend import DiscordClient, snowflake


def list_guilds(client: DiscordClient, limit: int = 100) -> list:
    return client.get("/users/@me/guilds", params={"limit": limit})


def get_guild(client: DiscordClient, guild_id: str) -> dict:
    return client.get(f"/guilds/{snowflake(guild_id, 'guild id')}", params={"with_counts": "true"})
