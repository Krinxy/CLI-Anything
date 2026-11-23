"""E2E tests: subprocess tests run the installed `cli-anything-discord` command.

Live tests need a throwaway bot and server and are skipped unless set:
  DISCORD_BOT_TOKEN, DISCORD_TEST_CHANNEL_ID  (and optionally DISCORD_WEBHOOK_URL)
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

LIVE = bool(os.environ.get("DISCORD_BOT_TOKEN") and os.environ.get("DISCORD_TEST_CHANNEL_ID"))
live = pytest.mark.skipif(not LIVE, reason="needs DISCORD_BOT_TOKEN and DISCORD_TEST_CHANNEL_ID")


def _resolve_cli(name="cli-anything-discord"):
    """Installed command if on PATH (or CLI_ANYTHING_FORCE_INSTALLED=1), else python -m."""
    exe = shutil.which(name)
    if exe:
        return [exe]
    if os.environ.get("CLI_ANYTHING_FORCE_INSTALLED"):
        raise RuntimeError(f"{name} not found on PATH")
    return [sys.executable, "-m", "cli_anything.discord"]


def run_cli(*args, env_extra=None, drop=()):
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update(env_extra or {})
    return subprocess.run(_resolve_cli() + list(args), capture_output=True, text=True, env=env, timeout=60)


def test_help():
    res = run_cli("--help")
    assert res.returncode == 0 and "message" in res.stdout


def test_missing_token_json_error():
    res = run_cli("--json", "whoami", drop=("DISCORD_BOT_TOKEN",))
    assert res.returncode == 1
    assert "DISCORD_BOT_TOKEN" in json.loads(res.stdout)["error"]


def test_invalid_channel_id_rejected_before_network():
    res = run_cli("--json", "message", "send", "../x", "hi", env_extra={"DISCORD_BOT_TOKEN": "t"})
    assert res.returncode == 1
    assert "Invalid channel id" in json.loads(res.stdout)["error"]


def test_non_discord_webhook_url_rejected():
    res = run_cli("--json", "webhook", "send", "hi",
                  env_extra={"DISCORD_WEBHOOK_URL": "https://evil.example/api/webhooks/1/t"})
    assert res.returncode == 1
    assert "Not a Discord webhook" in json.loads(res.stdout)["error"]


@live
def test_live_whoami_and_roundtrip():
    channel = os.environ["DISCORD_TEST_CHANNEL_ID"]
    who = json.loads(run_cli("--json", "whoami").stdout)
    assert who["bot"] is True
    sent = json.loads(run_cli("--json", "message", "send", channel, "cli-anything-discord e2e").stdout)
    hist = json.loads(run_cli("--json", "message", "history", channel, "--limit", "5").stdout)
    assert sent["id"] in [m["id"] for m in hist]
    assert json.loads(run_cli("--json", "message", "delete", channel, sent["id"]).stdout) == {"deleted": sent["id"]}


NETWORK = bool(os.environ.get("CLI_ANYTHING_NETWORK_TESTS"))
network = pytest.mark.skipif(not NETWORK, reason="set CLI_ANYTHING_NETWORK_TESTS=1 to call the real Discord API with invalid credentials")


@network
def test_network_invalid_token_is_reported_as_unauthorized():
    res = run_cli("--json", "whoami", env_extra={"DISCORD_BOT_TOKEN": "invalid-test-token"})
    assert res.returncode == 1
    assert "401" in json.loads(res.stdout)["error"]


@network
def test_network_unknown_webhook_is_a_clean_error():
    url = "https://discord.com/api/webhooks/123456789012345678/" + "fake" * 9
    res = run_cli("--json", "webhook", "send", "x", env_extra={"DISCORD_WEBHOOK_URL": url})
    assert res.returncode == 1
    assert "Unknown Webhook" in json.loads(res.stdout)["error"]
