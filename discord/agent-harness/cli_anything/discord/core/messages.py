"""Messages: send, read history, delete."""

from cli_anything.discord.utils.discord_backend import (
    DiscordClient, check_content, snowflake,
)

NO_MENTIONS = {"parse": []}


def allowed_mentions(allow: bool) -> dict | None:
    """Default: suppress @everyone/@role/@user pings so an agent cannot spam a server."""
    return None if allow else NO_MENTIONS


def send_message(client: DiscordClient, channel_id: str, content: str,
                 allow_mentions: bool = False) -> dict:
    body = {"content": check_content(content)}
    if (am := allowed_mentions(allow_mentions)) is not None:
        body["allowed_mentions"] = am
    return client.post(f"/channels/{snowflake(channel_id, 'channel id')}/messages", body)


def get_history(client: DiscordClient, channel_id: str, limit: int = 20,
                before: str | None = None) -> list:
    """Newest first. Message content is empty unless the bot has the MESSAGE_CONTENT intent."""
    params = {"limit": limit}
    if before:
        params["before"] = snowflake(before, "message id")
    return [{"id": m["id"], "author": m["author"].get("username"), "timestamp": m["timestamp"],
             "content": m.get("content", "")}
            for m in client.get(f"/channels/{snowflake(channel_id, 'channel id')}/messages", params=params)]


def delete_message(client: DiscordClient, channel_id: str, message_id: str) -> dict:
    client.delete(f"/channels/{snowflake(channel_id, 'channel id')}/messages/{snowflake(message_id, 'message id')}")
    return {"deleted": snowflake(message_id, "message id")}
