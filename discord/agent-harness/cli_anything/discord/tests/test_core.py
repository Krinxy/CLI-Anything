"""Unit tests for cli-anything-discord. No network and no real token needed."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cli_anything.discord.core import channels, guilds, messages, webhooks
from cli_anything.discord.discord_cli import cli
from cli_anything.discord.utils import discord_backend as backend
from cli_anything.discord.utils.discord_backend import (
    DiscordClient, RateLimited, check_content, check_webhook_url, snowflake,
)

TOKEN = "unit-test-token-123"
HOOK = "https://discord.com/api/webhooks/123/abcDEF"


def fake_response(status=200, body=None, reason="OK"):
    r = MagicMock()
    r.status_code = status
    r.ok = status < 400
    r.reason = reason
    r.content = b"x" if body is not None else b""
    r.json.return_value = body
    return r


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", TOKEN)
    c = DiscordClient()
    c.session = MagicMock()
    return c


# --- DiscordClient --------------------------------------------------------

def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="DISCORD_BOT_TOKEN"):
        DiscordClient()


def test_auth_header_set_from_env(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", TOKEN)
    assert DiscordClient().session.headers["Authorization"] == f"Bot {TOKEN}"


def test_get_builds_url_and_returns_json(client):
    client.session.request.return_value = fake_response(body={"id": "1"})
    assert client.get("/users/@me") == {"id": "1"}
    method, url = client.session.request.call_args.args
    assert (method, url) == ("GET", "https://discord.com/api/v10/users/@me")


def test_empty_body_returns_dict(client):
    client.session.request.return_value = fake_response(204, body=None)
    assert client.delete("/x") == {}


def test_rate_limit_raises_with_retry_after(client):
    client.session.request.return_value = fake_response(429, {"retry_after": 1.5})
    with pytest.raises(RateLimited) as exc:
        client.get("/x")
    assert exc.value.retry_after == 1.5
    assert client.session.request.call_count == 1  # never retried silently


def test_http_error_message_has_code_and_no_token(client):
    client.session.request.return_value = fake_response(403, {"message": "Missing Access", "code": 50001}, "Forbidden")
    with pytest.raises(RuntimeError) as exc:
        client.get("/x")
    assert "403" in str(exc.value) and "Missing Access" in str(exc.value)
    assert TOKEN not in str(exc.value)


def test_unauthorized_hints_env(client):
    client.session.request.return_value = fake_response(401, {"message": "401: Unauthorized", "code": 0})
    with pytest.raises(RuntimeError, match="DISCORD_BOT_TOKEN"):
        client.get("/x")


def test_network_error_wrapped(client):
    import requests
    client.session.request.side_effect = requests.exceptions.ConnectionError("boom")
    with pytest.raises(RuntimeError, match="Cannot reach"):
        client.get("/x")


# --- validation -----------------------------------------------------------

@pytest.mark.parametrize("bad", ["", "abc", "123/../x", "12 3", "1" * 21, "-1"])
def test_snowflake_rejects(bad):
    with pytest.raises(RuntimeError, match="Invalid"):
        snowflake(bad)


def test_snowflake_accepts():
    assert snowflake(" 1234567890123456789 ") == "1234567890123456789"


def test_content_limits():
    assert check_content("hi") == "hi"
    with pytest.raises(RuntimeError, match="empty"):
        check_content("   ")
    with pytest.raises(RuntimeError, match="too long"):
        check_content("x" * 2001)


@pytest.mark.parametrize("url", [
    "http://discord.com/api/webhooks/1/t",          # not https
    "https://evil.example/api/webhooks/1/t",         # wrong host
    "https://discord.com.evil.example/api/webhooks/1/t",
    "https://discord.com/api/v10/users/@me",         # wrong path
    "https://evil.example" + chr(92) + "@discord.com/api/webhooks/1/t",
    "https://user@discord.com/api/webhooks/1/t",
    "https://discord.com:8443/api/webhooks/1/t",
    "https://discord.com:abc/api/webhooks/1/t",
    "https://discord.com/api/webhooks/../v10/users/@me",
    "https://discord.com/api/webhooks/%2e%2e/t",
    "https://discord.com/api/webhooks/1/t?x=1",
    "https://discord.com/api/webhooks/1/t#frag",
    "https://discord.com/api/webhooks/notnumeric/t",
    "",
])
def test_webhook_url_rejected(url):
    with pytest.raises(RuntimeError, match="Not a Discord webhook"):
        check_webhook_url(url)


def test_webhook_url_refused_when_parsers_disagree():
    with patch.object(backend, "_requests_host", return_value="evil.example"):
        with pytest.raises(RuntimeError, match="Not a Discord webhook"):
            check_webhook_url("https://discord.com/api/webhooks/1/t")


def test_webhook_url_refused_when_requests_parser_rejects_it():
    with patch.object(backend, "parse_url", side_effect=backend.LocationParseError("x")):
        with pytest.raises(RuntimeError, match="Not a Discord webhook"):
            check_webhook_url("https://discord.com/api/webhooks/1/t")


def test_webhook_url_accepted():
    assert check_webhook_url(HOOK + "  ") == HOOK
    assert check_webhook_url("https://discord.com:443/api/webhooks/1/t")


def test_webhook_redirect_is_not_followed(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", HOOK)
    with patch.object(backend.requests.Session, "request", return_value=fake_response(302, body=None)) as req:
        with pytest.raises(RuntimeError, match="redirect"):
            webhooks.send_webhook("hi")
    assert req.call_args.kwargs["allow_redirects"] is False


# --- core -----------------------------------------------------------------

def test_send_message_suppresses_mentions_by_default(client):
    client.session.request.return_value = fake_response(body={"id": "9", "channel_id": "5"})
    messages.send_message(client, "5", "hello @everyone")
    kw = client.session.request.call_args.kwargs
    assert client.session.request.call_args.args == ("POST", "https://discord.com/api/v10/channels/5/messages")
    assert kw["json"] == {"content": "hello @everyone", "allowed_mentions": {"parse": []}}


def test_send_message_allow_mentions(client):
    client.session.request.return_value = fake_response(body={"id": "9", "channel_id": "5"})
    messages.send_message(client, "5", "hi", allow_mentions=True)
    assert "allowed_mentions" not in client.session.request.call_args.kwargs["json"]


def test_send_message_rejects_bad_channel_before_request(client):
    with pytest.raises(RuntimeError, match="Invalid channel id"):
        messages.send_message(client, "../guilds", "hi")
    client.session.request.assert_not_called()


def test_history_shape_and_params(client):
    client.session.request.return_value = fake_response(body=[
        {"id": "2", "author": {"username": "bob"}, "timestamp": "t", "content": "yo", "extra": 1},
    ])
    out = messages.get_history(client, "5", limit=3, before="7")
    assert out == [{"id": "2", "author": "bob", "timestamp": "t", "content": "yo"}]
    assert client.session.request.call_args.kwargs["params"] == {"limit": 3, "before": "7"}


def test_delete_message(client):
    client.session.request.return_value = fake_response(204, body=None)
    assert messages.delete_message(client, "5", "6") == {"deleted": "6"}
    assert client.session.request.call_args.args == ("DELETE", "https://discord.com/api/v10/channels/5/messages/6")


def test_list_channels_maps_types(client):
    client.session.request.return_value = fake_response(body=[{"id": "1", "name": "g", "type": 0, "parent_id": None}])
    assert channels.list_channels(client, "9")[0]["type"] == "text"


def test_list_guilds_and_get_guild(client):
    client.session.request.return_value = fake_response(body=[{"id": "1", "name": "A"}])
    assert guilds.list_guilds(client)[0]["name"] == "A"
    guilds.get_guild(client, "1")
    assert client.session.request.call_args.kwargs["params"] == {"with_counts": "true"}


def test_webhook_send_sends_no_authorization_header(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", HOOK)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", TOKEN)  # present in the environment, must still not be sent
    sent_headers = []

    def capture(self, *args, **kwargs):
        sent_headers.append(dict(self.headers))
        return fake_response(body={"id": "1"})

    with patch.object(backend.requests.Session, "request", autospec=True, side_effect=capture):
        webhooks.send_webhook("hi")
    assert not any(name.lower() == "authorization" for name in sent_headers[0])
    assert TOKEN not in json.dumps(sent_headers)


def test_non_json_200_is_an_error_not_a_string(client):
    r = fake_response(body=None)
    r.content, r.text = b"<html>login</html>", "<html>login</html>"
    r.json.side_effect = ValueError("not json")
    client.session.request.return_value = r
    with pytest.raises(RuntimeError, match="non-JSON"):
        client.get("/x")


def test_error_body_that_is_not_an_object_does_not_crash(client):
    client.session.request.return_value = fake_response(500, body=["unexpected"], reason="Server Error")
    with pytest.raises(RuntimeError, match="500"):
        client.get("/x")


def test_webhook_send_uses_no_bot_auth(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", HOOK)
    with patch.object(backend.requests.Session, "request", return_value=fake_response(body={"id": "1"})) as req:
        webhooks.send_webhook("hi", username="bot")
    assert req.call_args.args == ("POST", HOOK)
    assert req.call_args.kwargs["params"] == {"wait": "true"}
    assert req.call_args.kwargs["json"]["username"] == "bot"
    assert req.call_args.kwargs["json"]["allowed_mentions"] == {"parse": []}


def test_webhook_send_without_url(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    with pytest.raises(RuntimeError, match="DISCORD_WEBHOOK_URL"):
        webhooks.send_webhook("hi")


# --- CLI / --json ---------------------------------------------------------

def run(args, monkeypatch, response=None):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", TOKEN)
    with patch.object(backend.requests.Session, "request", return_value=response or fake_response(body={})):
        return CliRunner().invoke(cli, args, obj={})


def test_cli_whoami_json(monkeypatch):
    res = run(["--json", "whoami"], monkeypatch, fake_response(body={"id": "1", "username": "bot", "bot": True, "secret": "x"}))
    assert res.exit_code == 0
    assert json.loads(res.output) == {"id": "1", "username": "bot", "bot": True}


def test_cli_guild_list_json(monkeypatch):
    res = run(["--json", "guild", "list"], monkeypatch, fake_response(body=[{"id": "1", "name": "A", "icon": "z"}]))
    assert json.loads(res.output) == [{"id": "1", "name": "A"}]


def test_cli_message_send_json(monkeypatch):
    res = run(["--json", "message", "send", "5", "hi"], monkeypatch, fake_response(body={"id": "9", "channel_id": "5"}))
    assert json.loads(res.output) == {"id": "9", "channel_id": "5"}


def test_cli_history_limit_validated(monkeypatch):
    assert run(["message", "history", "5", "--limit", "101"], monkeypatch).exit_code == 2


def test_cli_has_no_token_flag(monkeypatch):
    assert run(["--token", "x", "whoami"], monkeypatch).exit_code == 2


def test_cli_help_lists_groups():
    out = CliRunner().invoke(cli, ["--help"]).output
    for word in ("whoami", "guild", "channel", "message", "webhook"):
        assert word in out
