"""Bot account info."""

from cli_anything.slack.utils.slack_backend import SlackClient


def whoami(client: SlackClient) -> dict:
    """Return the bot identity; also proves the token is valid."""
    return client.call("auth.test")
