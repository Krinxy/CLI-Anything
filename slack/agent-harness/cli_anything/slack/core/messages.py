"""Messages: send, read history, delete."""

from cli_anything.slack.utils.slack_backend import (
    SlackClient, channel_id, check_content, message_ts, neutralize_broadcasts,
)


def prepare_text(text: str, allow_mentions: bool) -> str:
    """Default: break <!channel>/<!here>/<!everyone> so an agent cannot ping a workspace."""
    text = check_content(text)
    return text if allow_mentions else neutralize_broadcasts(text)


def send_message(client: SlackClient, channel: str, text: str, thread_ts: str | None = None,
                 allow_mentions: bool = False) -> dict:
    body = {"channel": channel_id(channel), "text": prepare_text(text, allow_mentions)}
    if thread_ts:
        body["thread_ts"] = message_ts(thread_ts)
    data = client.call("chat.postMessage", body=body)
    return {"ts": data["ts"], "channel": data["channel"]}


def get_history(client: SlackClient, channel: str, limit: int = 20, latest: str | None = None) -> list:
    """Newest first. Needs channels:history (public) / groups:history (private) and bot membership."""
    params = {"channel": channel_id(channel), "limit": limit}
    if latest:
        params["latest"] = message_ts(latest)
    return [{"ts": m["ts"], "user": m.get("user") or m.get("bot_id"), "text": m.get("text", "")}
            for m in client.call("conversations.history", params)["messages"]]


def delete_message(client: SlackClient, channel: str, ts: str) -> dict:
    client.call("chat.delete", body={"channel": channel_id(channel), "ts": message_ts(ts)})
    return {"deleted": message_ts(ts)}
