"""E2E tests: subprocess tests run the installed `cli-anything-slack` command.

Live tests need a throwaway bot and server and are skipped unless set:
  SLACK_BOT_TOKEN, SLACK_TEST_CHANNEL_ID  (and optionally SLACK_WEBHOOK_URL)
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

LIVE = bool(os.environ.get("SLACK_BOT_TOKEN") and os.environ.get("SLACK_TEST_CHANNEL_ID"))
live = pytest.mark.skipif(not LIVE, reason="needs SLACK_BOT_TOKEN and SLACK_TEST_CHANNEL_ID")


def _resolve_cli(name="cli-anything-slack"):
    """Installed command if on PATH (or CLI_ANYTHING_FORCE_INSTALLED=1), else python -m."""
    exe = shutil.which(name)
    if exe:
        return [exe]
    if os.environ.get("CLI_ANYTHING_FORCE_INSTALLED"):
        raise RuntimeError(f"{name} not found on PATH")
    return [sys.executable, "-m", "cli_anything.slack"]


def run_cli(*args, env_extra=None, drop=()):
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update(env_extra or {})
    return subprocess.run(_resolve_cli() + list(args), capture_output=True, text=True, env=env, timeout=60)


def test_help():
    res = run_cli("--help")
    assert res.returncode == 0 and "message" in res.stdout


def test_missing_token_json_error():
    res = run_cli("--json", "whoami", drop=("SLACK_BOT_TOKEN",))
    assert res.returncode == 1
    assert "SLACK_BOT_TOKEN" in json.loads(res.stdout)["error"]


def test_invalid_channel_id_rejected_before_network():
    res = run_cli("--json", "message", "send", "../x", "hi", env_extra={"SLACK_BOT_TOKEN": "t"})
    assert res.returncode == 1
    assert "Invalid channel id" in json.loads(res.stdout)["error"]


def test_non_slack_webhook_url_rejected():
    res = run_cli("--json", "webhook", "send", "hi",
                  env_extra={"SLACK_WEBHOOK_URL": "https://evil.example/services/T/B/x"})
    assert res.returncode == 1
    assert "Not a Slack webhook" in json.loads(res.stdout)["error"]


@live
def test_live_whoami_and_roundtrip():
    channel = os.environ["SLACK_TEST_CHANNEL_ID"]
    who = json.loads(run_cli("--json", "whoami").stdout)
    assert who["user_id"]
    sent = json.loads(run_cli("--json", "message", "send", channel, "cli-anything-slack e2e").stdout)
    hist = json.loads(run_cli("--json", "message", "history", channel, "--limit", "5").stdout)
    assert sent["ts"] in [m["ts"] for m in hist]
    assert json.loads(run_cli("--json", "message", "delete", channel, sent["ts"]).stdout) == {"deleted": sent["ts"]}


NETWORK = bool(os.environ.get("CLI_ANYTHING_NETWORK_TESTS"))
network = pytest.mark.skipif(not NETWORK, reason="set CLI_ANYTHING_NETWORK_TESTS=1 to call the real Slack API with invalid credentials")


@network
def test_network_invalid_token_is_reported_as_invalid_auth():
    res = run_cli("--json", "whoami", env_extra={"SLACK_BOT_TOKEN": "invalid-test-token"})
    assert res.returncode == 1
    assert "invalid_auth" in json.loads(res.stdout)["error"]


@network
def test_network_unknown_webhook_is_a_clean_error():
    # Built at run time: a made-up URL, but the literal would match the shape of a real webhook and trip secret scanners.
    url = "https://hooks.slack.com/services/" + "/".join(["T" + "0" * 8, "B" + "0" * 8, "X" * 24])
    res = run_cli("--json", "webhook", "send", "x", env_extra={"SLACK_WEBHOOK_URL": url})
    assert res.returncode == 1
    assert "404" in json.loads(res.stdout)["error"]
