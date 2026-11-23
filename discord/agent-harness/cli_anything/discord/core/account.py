"""Bot account info."""

from cli_anything.discord.utils.discord_backend import DiscordClient


def whoami(client: DiscordClient) -> dict:
    """Return the bot user; also proves the token is valid."""
    return client.get("/users/@me")
