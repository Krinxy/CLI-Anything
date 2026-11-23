"""Conversations (channels) visible to the bot."""

from cli_anything.slack.utils.slack_backend import SlackClient, channel_id


def list_channels(client: SlackClient, limit: int = 100, include_private: bool = False) -> list:
    types = "public_channel,private_channel" if include_private else "public_channel"
    data = client.call("conversations.list", {"limit": limit, "types": types, "exclude_archived": "true"})
    return [{"id": c["id"], "name": c.get("name"), "is_private": c.get("is_private", False),
             "num_members": c.get("num_members")} for c in data["channels"]]


def get_channel(client: SlackClient, channel: str) -> dict:
    return client.call("conversations.info", {"channel": channel_id(channel)})["channel"]
