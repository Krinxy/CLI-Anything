"""Send through a channel webhook (no bot needed). The URL comes from DISCORD_WEBHOOK_URL."""

import os

from cli_anything.discord.core.messages import allowed_mentions
from cli_anything.discord.utils.discord_backend import (
    WEBHOOK_ENV, check_content, post_webhook,
)


def send_webhook(content: str, username: str | None = None, url: str | None = None,
                 allow_mentions: bool = False) -> dict:
    url = url or os.environ.get(WEBHOOK_ENV, "")
    payload = {"content": check_content(content)}
    if username:
        payload["username"] = username
    if (am := allowed_mentions(allow_mentions)) is not None:
        payload["allowed_mentions"] = am
    return post_webhook(url, payload)
