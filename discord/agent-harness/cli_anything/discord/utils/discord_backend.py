"""Discord REST API v10 client - wraps all calls to the real Discord service.

Security notes:
- The bot token is read from the DISCORD_BOT_TOKEN environment variable only
  (never from argv or files) and is never included in error messages.
- IDs are validated as snowflakes before they reach a URL path.
- Webhook URLs are credentials; they are validated against Discord's hosts
  so a token can never be posted to an arbitrary server.
- A 429 is surfaced to the caller (with retry_after) instead of being retried.
"""

import os
import re
from typing import Any
from urllib.parse import urlparse

import requests
from urllib3.util import parse_url
from urllib3.exceptions import LocationParseError

API_BASE = "https://discord.com/api/v10"
TOKEN_ENV = "DISCORD_BOT_TOKEN"
WEBHOOK_ENV = "DISCORD_WEBHOOK_URL"
MAX_CONTENT = 2000
USER_AGENT = "DiscordBot (https://github.com/HKUDS/CLI-Anything, 1.0.0)"
WEBHOOK_HOSTS = {"discord.com", "ptb.discord.com", "canary.discord.com", "discordapp.com"}
BACKSLASH = chr(92)
_WEBHOOK_PATH = re.compile(r"^/api/webhooks/[0-9]{1,20}/[A-Za-z0-9_-]+$")
_SNOWFLAKE = re.compile(r"^\d{1,20}$")


class RateLimited(RuntimeError):
    """Discord answered 429; retry_after is in seconds."""

    def __init__(self, retry_after: float):
        super().__init__(f"Rate limited by Discord. Retry after {retry_after}s.")
        self.retry_after = retry_after


def snowflake(value: Any, what: str = "id") -> str:
    """Return value as a validated Discord snowflake string (digits only)."""
    text = str(value).strip()
    if not _SNOWFLAKE.match(text):
        raise RuntimeError(f"Invalid {what} {text!r}: expected a numeric Discord ID.")
    return text


def check_content(content: str) -> str:
    if not content or not content.strip():
        raise RuntimeError("Message content must not be empty.")
    if len(content) > MAX_CONTENT:
        raise RuntimeError(f"Message too long ({len(content)} > {MAX_CONTENT} characters).")
    return content


def _error(resp: requests.Response) -> RuntimeError:
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    if resp.status_code == 429:
        return RateLimited(float(body.get("retry_after", 0)))
    hint = ""
    if resp.status_code == 401:
        hint = f" Check {TOKEN_ENV}."
    elif resp.status_code == 403:
        hint = " The bot lacks permission or is not in that guild/channel."
    return RuntimeError(
        f"Discord API error {resp.status_code}: {body.get('message', resp.reason)} "
        f"(code {body.get('code', 'n/a')}).{hint}"
    )


def _send(session: requests.Session, method: str, url: str, **kwargs: Any) -> Any:
    try:
        resp = session.request(method, url, timeout=10, **kwargs)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Cannot reach the Discord API ({type(e).__name__}). Check your network.")
    if not resp.ok:
        raise _error(resp)
    if 300 <= resp.status_code < 400:
        raise RuntimeError(f"Discord answered with a redirect ({resp.status_code}); refusing to follow it.")
    if not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError:  # a proxy or captive portal answering 200 with HTML
        raise RuntimeError("Discord returned a non-JSON response.")


class DiscordClient:
    """HTTP client for the Discord bot REST API."""

    def __init__(self, token: str | None = None, base_url: str = API_BASE):
        token = (token or os.environ.get(TOKEN_ENV, "")).strip()
        if not token:
            raise RuntimeError(
                f"No bot token. Set the {TOKEN_ENV} environment variable.\n"
                "Create a bot at https://discord.com/developers/applications, copy its token, "
                "and invite it to your server with the permissions you need."
            )
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bot {token}",
            "User-Agent": USER_AGENT,
        })

    def request(self, method: str, path: str, params: dict | None = None, body: Any = None) -> Any:
        return _send(self.session, method, f"{self.base_url}/{path.lstrip('/')}",
                     params=params, json=body)

    def get(self, path: str, params: dict | None = None) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, body: Any = None) -> Any:
        return self.request("POST", path, body=body)

    def put(self, path: str) -> Any:
        return self.request("PUT", path)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)


def _requests_host(url: str) -> str | None:
    """Host as the parser inside requests (urllib3) sees it; compared with urlparse's view."""
    try:
        return parse_url(url).host
    except LocationParseError:
        return None


def check_webhook_url(url: str) -> str:
    """Accept only https://<discord host>/api/webhooks/<id>/<token> URLs.

    urlparse and the parser inside requests can disagree on odd URLs (a backslash or userinfo
    before the host), so those forms are refused outright; so are ports other than 443, query
    strings, fragments and any path that is not exactly /api/webhooks/<numeric id>/<token>.
    """
    url = url.strip()
    parts = urlparse(url)
    try:
        port = parts.port
    except ValueError:  # e.g. "https://discord.com:abc/..."
        port = -1
    if (parts.scheme != "https" or parts.hostname not in WEBHOOK_HOSTS or port not in (None, 443)
            or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment or BACKSLASH in url
            or not _WEBHOOK_PATH.match(parts.path) or _requests_host(url) != parts.hostname):
        raise RuntimeError(
            f"Not a Discord webhook URL. Set {WEBHOOK_ENV} to "
            "https://discord.com/api/webhooks/<id>/<token>."
        )
    return url


def post_webhook(url: str, payload: dict) -> Any:
    """POST to a webhook. The URL carries the credential, so no auth header is sent."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    data = _send(session, "POST", check_webhook_url(url), params={"wait": "true"}, json=payload,
                 allow_redirects=False)
    if not isinstance(data, dict):
        raise RuntimeError("Discord webhook returned an unexpected response.")
    return data
