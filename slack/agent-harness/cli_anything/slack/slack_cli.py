"""cli-anything-slack - CLI harness for Slack (bot Web API + incoming webhooks)."""

import json
import shlex
import sys

import click
import requests

from cli_anything.slack.core import account as account_core
from cli_anything.slack.core import channels as channels_core
from cli_anything.slack.core import messages as messages_core
from cli_anything.slack.core import webhooks as webhooks_core
from cli_anything.slack.utils.repl_skin import ReplSkin
from cli_anything.slack.utils.slack_backend import SlackClient

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}
VERSION = "1.0.0"
MENTIONS_HELP = "Allow <!channel>/<!here>/<!everyone> pings (broken by default)"


def make_client(ctx: click.Context) -> SlackClient:
    # Token comes from SLACK_BOT_TOKEN only; there is deliberately no --token flag
    # (argv ends up in shell history and process listings).
    return SlackClient()


def output(data, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(data, indent=2, default=str))
    elif isinstance(data, dict):
        for k, v in data.items():
            click.echo(f"{k}: {v}")
    elif isinstance(data, list):
        for item in data:
            click.echo(json.dumps(item, default=str) if isinstance(item, dict) else str(item))
    else:
        click.echo(str(data))


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------

@click.group(context_settings=CONTEXT_SETTINGS, invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.pass_context
def cli(ctx: click.Context, as_json: bool):
    """cli-anything-slack - control Slack from the command line.

    Auth: set SLACK_BOT_TOKEN (bot commands) or SLACK_WEBHOOK_URL (webhook send).
    """
    ctx.ensure_object(dict)
    ctx.obj["as_json"] = as_json
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


def main():
    try:
        cli(obj={})
    except (RuntimeError, requests.exceptions.RequestException) as exc:
        # Backend failures arrive as exceptions; surface them as parsable JSON with --json.
        # sys.argv is used because the Click context is already unwound here.
        if "--json" in sys.argv:
            click.echo(json.dumps({"error": str(exc)}, default=str))
        else:
            click.echo(str(exc), err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------

@cli.command(hidden=True)
@click.pass_context
def repl(ctx: click.Context):
    """Interactive REPL mode."""
    skin = ReplSkin("slack", version=VERSION)
    skin.print_banner()
    pt_session = skin.create_prompt_session()

    while True:
        try:
            line = skin.get_input(pt_session, project_name="slack")
        except (EOFError, KeyboardInterrupt):
            break

        line = line.strip()
        if not line:
            continue
        if line in ("exit", "quit"):
            break
        if line == "help":
            skin.help({
                "whoami": "Show the bot identity (validates the token)",
                "channel list/info": "Channels visible to the bot",
                "message send/history/delete": "Read and write messages",
                "webhook send": "Send via SLACK_WEBHOOK_URL",
            })
            continue

        try:
            cli.main(args=shlex.split(line), obj=dict(ctx.obj), standalone_mode=False)
        except click.exceptions.UsageError as e:
            skin.error(str(e))
        except (RuntimeError, requests.exceptions.RequestException) as e:
            skin.error(str(e))
        except SystemExit:
            pass
        except Exception as e:
            skin.error(f"Unexpected error: {e}")

    skin.print_goodbye()


# ---------------------------------------------------------------------------
# whoami
# ---------------------------------------------------------------------------

@cli.command()
@click.pass_context
def whoami(ctx: click.Context):
    """Show the bot identity (validates the token)."""
    data = account_core.whoami(make_client(ctx))
    output({k: data.get(k) for k in ("user", "user_id", "team", "team_id", "bot_id")}, ctx.obj["as_json"])


# ---------------------------------------------------------------------------
# channel
# ---------------------------------------------------------------------------

@cli.group()
def channel():
    """Channels visible to the bot."""


@channel.command("list")
@click.option("--limit", default=100, show_default=True, type=click.IntRange(1, 1000))
@click.option("--private", "include_private", is_flag=True, default=False,
              help="Also list private channels (needs groups:read)")
@click.pass_context
def channel_list(ctx: click.Context, limit: int, include_private: bool):
    """List channels."""
    output(channels_core.list_channels(make_client(ctx), limit, include_private), ctx.obj["as_json"])


@channel.command("info")
@click.argument("channel_id")
@click.pass_context
def channel_info(ctx: click.Context, channel_id: str):
    """Show one channel."""
    c = channels_core.get_channel(make_client(ctx), channel_id)
    output({k: c.get(k) for k in ("id", "name", "is_private", "num_members", "topic")}, ctx.obj["as_json"])


# ---------------------------------------------------------------------------
# message
# ---------------------------------------------------------------------------

@cli.group()
def message():
    """Send, read and delete messages."""


@message.command("send")
@click.argument("channel_id")
@click.argument("text")
@click.option("--thread", "thread_ts", default=None, help="Reply in the thread of this message ts")
@click.option("--allow-mentions", is_flag=True, default=False, help=MENTIONS_HELP)
@click.pass_context
def message_send(ctx: click.Context, channel_id: str, text: str, thread_ts: str | None, allow_mentions: bool):
    """Send TEXT to a channel (the bot must be a member)."""
    output(messages_core.send_message(make_client(ctx), channel_id, text, thread_ts, allow_mentions),
           ctx.obj["as_json"])


@message.command("history")
@click.argument("channel_id")
@click.option("--limit", default=20, show_default=True, type=click.IntRange(1, 999))
@click.option("--latest", default=None, help="Only messages older than this ts")
@click.pass_context
def message_history(ctx: click.Context, channel_id: str, limit: int, latest: str | None):
    """Show recent messages, newest first (needs channels:history and bot membership)."""
    output(messages_core.get_history(make_client(ctx), channel_id, limit, latest), ctx.obj["as_json"])


@message.command("delete")
@click.argument("channel_id")
@click.argument("ts")
@click.pass_context
def message_delete(ctx: click.Context, channel_id: str, ts: str):
    """Delete a message (a bot can delete its own; others need chat:write admin rights)."""
    output(messages_core.delete_message(make_client(ctx), channel_id, ts), ctx.obj["as_json"])


# ---------------------------------------------------------------------------
# webhook
# ---------------------------------------------------------------------------

@cli.group()
def webhook():
    """Send through an incoming webhook (no bot needed)."""


@webhook.command("send")
@click.argument("text")
@click.option("--allow-mentions", is_flag=True, default=False, help=MENTIONS_HELP)
@click.pass_context
def webhook_send(ctx: click.Context, text: str, allow_mentions: bool):
    """Send TEXT using the webhook in SLACK_WEBHOOK_URL."""
    output(webhooks_core.send_webhook(text, allow_mentions=allow_mentions), ctx.obj["as_json"])


if __name__ == "__main__":
    main()
