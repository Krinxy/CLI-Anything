"""Send through an incoming webhook (no bot needed). The URL comes from SLACK_WEBHOOK_URL."""

import os

from cli_anything.slack.core.messages import prepare_text
from cli_anything.slack.utils.slack_backend import WEBHOOK_ENV, post_webhook


def send_webhook(text: str, url: str | None = None, allow_mentions: bool = False) -> dict:
    url = url or os.environ.get(WEBHOOK_ENV, "")
    return post_webhook(url, {"text": prepare_text(text, allow_mentions)})
