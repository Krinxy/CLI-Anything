"""Slack Web API client - wraps all calls to the real Slack service.

Security notes:
- The bot token is read from the SLACK_BOT_TOKEN environment variable only
  (never from argv or files) and is never included in error messages.
- Channel IDs and message timestamps are validated before they are sent.
- Webhook URLs are credentials; they are validated against hooks.slack.com
  so a secret can never be posted to an arbitrary server.
- A 429 is surfaced to the caller (with Retry-After) instead of being retried.
- Slack reports most failures as HTTP 200 with {"ok": false, "error": ...},
  so every response is checked for "ok".
"""

import os
import re
from typing import Any
from urllib.parse import urlparse

import requests
from urllib3.util import parse_url
from urllib3.exceptions import LocationParseError

API_BASE = "https://slack.com/api"
TOKEN_ENV = "SLACK_BOT_TOKEN"
WEBHOOK_ENV = "SLACK_WEBHOOK_URL"
MAX_CONTENT = 40000  # chat.postMessage truncates beyond this
USER_AGENT = "cli-anything-slack/1.0.0 (+https://github.com/HKUDS/CLI-Anything)"
WEBHOOK_HOST = "hooks.slack.com"
ZERO_WIDTH_SPACE = chr(0x200B)
BACKSLASH = chr(92)
_WEBHOOK_PATH = re.compile(r"^/services/[A-Za-z0-9]+/[A-Za-z0-9]+/[A-Za-z0-9]+$")
_CHANNEL_ID = re.compile(r"^[CDG][A-Z0-9]{2,20}$")
_TS = re.compile(r"^\d{1,12}\.\d{1,8}$")

_HINTS = {
    "not_authed": f"Set {TOKEN_ENV}.",
    "invalid_auth": f"Check {TOKEN_ENV}.",
    "token_revoked": f"Check {TOKEN_ENV}.",
    "not_in_channel": "Invite the bot to the channel first (/invite @bot).",
    "channel_not_found": "Check the channel ID, or invite the bot to a private channel.",
}


class RateLimited(RuntimeError):
    """Slack answered 429; retry_after is in seconds."""

    def __init__(self, retry_after: float):
        super().__init__(f"Rate limited by Slack. Retry after {retry_after}s.")
        self.retry_after = retry_after


def channel_id(value: Any) -> str:
    """Return value as a validated Slack conversation ID (C..., G..., D...)."""
    text = str(value).strip()
    if not _CHANNEL_ID.match(text):
        raise RuntimeError(f"Invalid channel id {text!r}: expected an ID like C0123456789 (not a #name).")
    return text


def message_ts(value: Any) -> str:
    """Return value as a validated message timestamp like 1712345678.000100."""
    text = str(value).strip()
    if not _TS.match(text):
        raise RuntimeError(f"Invalid message ts {text!r}: expected digits like 1712345678.000100.")
    return text


def check_content(content: str) -> str:
    if not content or not content.strip():
        raise RuntimeError("Message text must not be empty.")
    if len(content) > MAX_CONTENT:
        raise RuntimeError(f"Message too long ({len(content)} > {MAX_CONTENT} characters).")
    return content


def neutralize_broadcasts(text: str) -> str:
    """Break <!channel>, <!here>, <!everyone> and <!subteam^..> so they do not ping."""
    return text.replace("<!", "<" + ZERO_WIDTH_SPACE + "!")


def _retry_after(resp: requests.Response) -> float:
    try:
        return float(resp.headers.get("Retry-After", 0))
    except ValueError:
        return 0.0


def _api_error(data: dict) -> RuntimeError:
    code = data.get("error", "unknown_error")
    extra = f" (needs scope: {data['needed']})" if data.get("needed") else ""
    hint = f" {_HINTS[code]}" if code in _HINTS else ""
    return RuntimeError(f"Slack API error: {code}{extra}.{hint}")


def _send(session: requests.Session, method: str, url: str, **kwargs: Any) -> Any:
    try:
        resp = session.request(method, url, timeout=10, **kwargs)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Cannot reach the Slack API ({type(e).__name__}). Check your network.")
    if resp.status_code == 429:
        raise RateLimited(_retry_after(resp))
    if not resp.ok:
        raise RuntimeError(f"Slack HTTP error {resp.status_code}: {resp.reason}.")
    return resp


class SlackClient:
    """HTTP client for the Slack Web API (bot token)."""

    def __init__(self, token: str | None = None, base_url: str = API_BASE):
        token = (token or os.environ.get(TOKEN_ENV, "")).strip()
        if not token:
            raise RuntimeError(
                f"No bot token. Set the {TOKEN_ENV} environment variable.\n"
                "Create an app at https://api.slack.com/apps, add the scopes you need "
                "(chat:write, channels:read, channels:history), install it and copy the Bot User OAuth Token."
            )
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
        })

    def call(self, api_method: str, params: dict | None = None, body: dict | None = None) -> dict:
        """GET with params, or POST a JSON body. Raises unless Slack answers ok."""
        url = f"{self.base_url}/{api_method}"
        if body is not None:
            resp = _send(self.session, "POST", url, json=body)
        else:
            resp = _send(self.session, "GET", url, params=params)
        try:
            data = resp.json()
        except ValueError:
            raise RuntimeError("Slack returned a non-JSON response.")
        if not data.get("ok"):
            raise _api_error(data)
        return data


def _requests_host(url: str) -> str | None:
    """Host as the parser inside requests (urllib3) sees it; compared with urlparse's view."""
    try:
        return parse_url(url).host
    except LocationParseError:
        return None


def check_webhook_url(url: str) -> str:
    """Accept only https://hooks.slack.com/services/<T>/<B>/<token> URLs.

    urlparse and the parser inside requests can disagree on odd URLs (a backslash or userinfo
    before the host), so those forms are refused outright; so are ports other than 443, query
    strings, fragments and any path that is not exactly three alphanumeric segments (no "..").
    """
    url = url.strip()
    parts = urlparse(url)
    try:
        port = parts.port
    except ValueError:  # e.g. "https://hooks.slack.com:abc/..."
        port = -1
    if (parts.scheme != "https" or parts.hostname != WEBHOOK_HOST or port not in (None, 443)
            or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment or BACKSLASH in url
            or not _WEBHOOK_PATH.match(parts.path) or _requests_host(url) != parts.hostname):
        raise RuntimeError(
            f"Not a Slack webhook URL. Set {WEBHOOK_ENV} to "
            "https://hooks.slack.com/services/<T>/<B>/<token>."
        )
    return url


def post_webhook(url: str, payload: dict) -> dict:
    """POST to an incoming webhook. The URL carries the credential, so no auth header is sent."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    resp = _send(session, "POST", check_webhook_url(url), json=payload, allow_redirects=False)
    if 300 <= resp.status_code < 400:
        raise RuntimeError("Slack webhook answered with a redirect; refusing to follow it.")
    body = resp.text.strip()
    if body != "ok":  # Slack answers a delivered webhook with exactly "ok"; anything else is not a delivery
        raise RuntimeError(f"Slack webhook did not answer ok ({body[:60]!r}).")
    return {"ok": True}
