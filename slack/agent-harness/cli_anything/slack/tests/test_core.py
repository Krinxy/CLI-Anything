"""Unit tests for cli-anything-slack. No network and no real token needed."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cli_anything.slack.core import account, channels, messages, webhooks
from cli_anything.slack.slack_cli import cli
from cli_anything.slack.utils import slack_backend as backend
from cli_anything.slack.utils.slack_backend import (
    RateLimited, SlackClient, channel_id, check_content, check_webhook_url,
    message_ts, neutralize_broadcasts,
)

TOKEN = "fake-unit-test-token"
HOOK = "https://hooks.slack.com/services/T000/B000/abcDEF"
ZWSP = chr(0x200B)


def fake_response(body=None, status=200, headers=None, text=None, reason="OK"):
    r = MagicMock()
    r.status_code = status
    r.ok = status < 400
    r.reason = reason
    r.headers = headers or {}
    r.text = text if text is not None else json.dumps(body)
    if body is None and text is not None:
        r.json.side_effect = ValueError("not json")
    else:
        r.json.return_value = body
    return r


def ok(**extra):
    return fake_response({"ok": True, **extra})


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", TOKEN)
    c = SlackClient()
    c.session = MagicMock()
    return c


# --- SlackClient ----------------------------------------------------------

def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="SLACK_BOT_TOKEN"):
        SlackClient()


def test_auth_header_set_from_env(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", TOKEN)
    assert SlackClient().session.headers["Authorization"] == f"Bearer {TOKEN}"


def test_get_call_builds_url_and_params(client):
    client.session.request.return_value = ok(user="bot")
    assert client.call("auth.test")["user"] == "bot"
    assert client.session.request.call_args.args == ("GET", "https://slack.com/api/auth.test")


def test_post_call_sends_json(client):
    client.session.request.return_value = ok()
    client.call("chat.postMessage", body={"channel": "C1"})
    assert client.session.request.call_args.args[0] == "POST"
    assert client.session.request.call_args.kwargs["json"] == {"channel": "C1"}


def test_ok_false_raises_with_hint_and_no_token(client):
    client.session.request.return_value = fake_response({"ok": False, "error": "not_in_channel"})
    with pytest.raises(RuntimeError) as exc:
        client.call("chat.postMessage", body={})
    assert "not_in_channel" in str(exc.value) and "invite" in str(exc.value).lower()
    assert TOKEN not in str(exc.value)


def test_missing_scope_names_needed_scope(client):
    client.session.request.return_value = fake_response({"ok": False, "error": "missing_scope", "needed": "chat:write"})
    with pytest.raises(RuntimeError, match="chat:write"):
        client.call("chat.postMessage", body={})


def test_rate_limit_uses_retry_after_header_and_is_not_retried(client):
    client.session.request.return_value = fake_response({}, status=429, headers={"Retry-After": "7"})
    with pytest.raises(RateLimited) as exc:
        client.call("conversations.list")
    assert exc.value.retry_after == 7.0
    assert client.session.request.call_count == 1


def test_http_error_wrapped(client):
    client.session.request.return_value = fake_response({}, status=500, reason="Server Error")
    with pytest.raises(RuntimeError, match="500"):
        client.call("auth.test")


def test_non_json_response_rejected(client):
    client.session.request.return_value = fake_response(text="<html>")
    with pytest.raises(RuntimeError, match="non-JSON"):
        client.call("auth.test")


def test_network_error_wrapped(client):
    import requests
    client.session.request.side_effect = requests.exceptions.ConnectionError("boom")
    with pytest.raises(RuntimeError, match="Cannot reach"):
        client.call("auth.test")


# --- validation -----------------------------------------------------------

@pytest.mark.parametrize("bad", ["", "#general", "general", "c0123456789", "C01/../x", "X0123456789", "C" + "1" * 30])
def test_channel_id_rejects(bad):
    with pytest.raises(RuntimeError, match="Invalid channel id"):
        channel_id(bad)


@pytest.mark.parametrize("good", ["C0123456789", "G0123456789", "D0123456789"])
def test_channel_id_accepts(good):
    assert channel_id(f" {good} ") == good


@pytest.mark.parametrize("bad", ["", "abc", "123", "1712345678.0001/../x", "-1.2"])
def test_message_ts_rejects(bad):
    with pytest.raises(RuntimeError, match="Invalid message ts"):
        message_ts(bad)


def test_message_ts_accepts():
    assert message_ts("1712345678.000100") == "1712345678.000100"


def test_content_limits():
    assert check_content("hi") == "hi"
    with pytest.raises(RuntimeError, match="empty"):
        check_content("  ")
    with pytest.raises(RuntimeError, match="too long"):
        check_content("x" * 40001)


def test_neutralize_broadcasts_breaks_all_special_mentions():
    out = neutralize_broadcasts("<!channel> <!here> <!everyone> <!subteam^S1> <@U1> plain")
    assert "<!" not in out
    assert out.count("<" + ZWSP + "!") == 4
    assert "<@U1>" in out  # a single targeted user mention is kept


@pytest.mark.parametrize("url", [
    "http://hooks.slack.com/services/T/B/x",
    "https://evil.example/services/T/B/x",
    "https://hooks.slack.com.evil.example/services/T/B/x",
    "https://slack.com/api/auth.test",
    "https://evil.example" + chr(92) + "@hooks.slack.com/services/T/B/x",
    "https://user@hooks.slack.com/services/T/B/x",
    "https://user:pw@hooks.slack.com/services/T/B/x",
    "https://hooks.slack.com:8443/services/T/B/x",
    "https://hooks.slack.com:abc/services/T/B/x",
    "https://hooks.slack.com/services/../api/x",
    "https://hooks.slack.com/services/%2e%2e/B/x",
    "https://hooks.slack.com/services/T/B/x?x=1",
    "https://hooks.slack.com/services/T/B/x#frag",
    "https://hooks.slack.com/services/T/B",
    "",
])
def test_webhook_url_rejected(url):
    with pytest.raises(RuntimeError, match="Not a Slack webhook"):
        check_webhook_url(url)


def test_webhook_url_refused_when_parsers_disagree():
    with patch.object(backend, "_requests_host", return_value="evil.example"):
        with pytest.raises(RuntimeError, match="Not a Slack webhook"):
            check_webhook_url("https://hooks.slack.com/services/T/B/x")


def test_webhook_url_refused_when_requests_parser_rejects_it():
    with patch.object(backend, "parse_url", side_effect=backend.LocationParseError("x")):
        with pytest.raises(RuntimeError, match="Not a Slack webhook"):
            check_webhook_url("https://hooks.slack.com/services/T/B/x")


def test_webhook_url_accepted():
    assert check_webhook_url(HOOK + " ") == HOOK
    assert check_webhook_url("https://hooks.slack.com:443/services/T/B/x")


def test_webhook_redirect_is_not_followed(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", HOOK)
    with patch.object(backend.requests.Session, "request", return_value=fake_response(text="", status=302)) as req:
        with pytest.raises(RuntimeError, match="redirect"):
            webhooks.send_webhook("hi")
    assert req.call_args.kwargs["allow_redirects"] is False


# --- core -----------------------------------------------------------------

def test_whoami(client):
    client.session.request.return_value = ok(user="bot", team="T")
    assert account.whoami(client)["team"] == "T"


def test_list_channels_public_by_default(client):
    client.session.request.return_value = ok(channels=[{"id": "C1", "name": "g", "is_private": False, "num_members": 3, "x": 1}])
    out = channels.list_channels(client)
    assert out == [{"id": "C1", "name": "g", "is_private": False, "num_members": 3}]
    assert client.session.request.call_args.kwargs["params"]["types"] == "public_channel"


def test_list_channels_private_opt_in(client):
    client.session.request.return_value = ok(channels=[])
    channels.list_channels(client, include_private=True)
    assert client.session.request.call_args.kwargs["params"]["types"] == "public_channel,private_channel"


def test_send_message_breaks_broadcasts_by_default(client):
    client.session.request.return_value = ok(ts="1.2", channel="C0123456789")
    messages.send_message(client, "C0123456789", "hey <!channel>")
    body = client.session.request.call_args.kwargs["json"]
    assert "<!" not in body["text"] and body["channel"] == "C0123456789"


def test_send_message_allow_mentions_keeps_text(client):
    client.session.request.return_value = ok(ts="1.2", channel="C0123456789")
    messages.send_message(client, "C0123456789", "hey <!here>", allow_mentions=True)
    assert client.session.request.call_args.kwargs["json"]["text"] == "hey <!here>"


def test_send_message_thread(client):
    client.session.request.return_value = ok(ts="1.2", channel="C0123456789")
    messages.send_message(client, "C0123456789", "hi", thread_ts="1712345678.000100")
    assert client.session.request.call_args.kwargs["json"]["thread_ts"] == "1712345678.000100"


def test_send_message_rejects_bad_channel_before_request(client):
    with pytest.raises(RuntimeError, match="Invalid channel id"):
        messages.send_message(client, "#general", "hi")
    client.session.request.assert_not_called()


def test_history_shape_params_and_bot_fallback(client):
    client.session.request.return_value = ok(messages=[
        {"ts": "2.0", "user": "U1", "text": "yo", "extra": 1},
        {"ts": "1.0", "bot_id": "B1", "text": "beep"},
    ])
    out = messages.get_history(client, "C0123456789", limit=3, latest="1712345678.000100")
    assert out == [{"ts": "2.0", "user": "U1", "text": "yo"}, {"ts": "1.0", "user": "B1", "text": "beep"}]
    assert client.session.request.call_args.kwargs["params"] == {
        "channel": "C0123456789", "limit": 3, "latest": "1712345678.000100"}


def test_delete_message(client):
    client.session.request.return_value = ok()
    assert messages.delete_message(client, "C0123456789", "1712345678.000100") == {"deleted": "1712345678.000100"}
    assert client.session.request.call_args.args == ("POST", "https://slack.com/api/chat.delete")


def test_webhook_send_uses_no_bot_auth(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", HOOK)
    monkeypatch.setenv("SLACK_BOT_TOKEN", TOKEN)  # present in the environment, must still not be sent
    sent_headers = []

    def capture(self, *args, **kwargs):
        sent_headers.append(dict(self.headers))
        return fake_response(text="ok")

    with patch.object(backend.requests.Session, "request", autospec=True, side_effect=capture) as req:
        assert webhooks.send_webhook("hi <!channel>") == {"ok": True}
    assert req.call_args.args[1:] == ("POST", HOOK)
    assert "<!" not in req.call_args.kwargs["json"]["text"]
    assert not any(name.lower() == "authorization" for name in sent_headers[0])
    assert TOKEN not in json.dumps(sent_headers)


@pytest.mark.parametrize("body", ["", "no_service", "<html>login</html>"])
def test_webhook_200_without_ok_is_not_a_success(monkeypatch, body):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", HOOK)
    with patch.object(backend.requests.Session, "request", return_value=fake_response(text=body)):
        with pytest.raises(RuntimeError, match="did not answer ok"):
            webhooks.send_webhook("hi")


def test_webhook_send_without_url(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    with pytest.raises(RuntimeError, match="SLACK_WEBHOOK_URL"):
        webhooks.send_webhook("hi")


# --- CLI / --json ---------------------------------------------------------

def run(args, monkeypatch, response):
    monkeypatch.setenv("SLACK_BOT_TOKEN", TOKEN)
    with patch.object(backend.requests.Session, "request", return_value=response):
        return CliRunner().invoke(cli, args, obj={})


def test_cli_whoami_json(monkeypatch):
    res = run(["--json", "whoami"], monkeypatch, ok(user="bot", user_id="U1", team="T", team_id="T1", bot_id="B1", url="x"))
    assert res.exit_code == 0
    assert json.loads(res.output)["user_id"] == "U1" and "url" not in json.loads(res.output)


def test_cli_channel_list_json(monkeypatch):
    res = run(["--json", "channel", "list"], monkeypatch, ok(channels=[{"id": "C1", "name": "g"}]))
    assert json.loads(res.output)[0]["id"] == "C1"


def test_cli_message_send_json(monkeypatch):
    res = run(["--json", "message", "send", "C0123456789", "hi"], monkeypatch, ok(ts="1.2", channel="C0123456789"))
    assert json.loads(res.output) == {"ts": "1.2", "channel": "C0123456789"}


def test_cli_history_limit_validated(monkeypatch):
    assert run(["message", "history", "C0123456789", "--limit", "1000"], monkeypatch, ok(messages=[])).exit_code == 2


def test_cli_has_no_token_flag(monkeypatch):
    assert run(["--token", "x", "whoami"], monkeypatch, ok()).exit_code == 2


def test_cli_help_lists_groups():
    out = CliRunner().invoke(cli, ["--help"]).output
    for word in ("whoami", "channel", "message", "webhook"):
        assert word in out
