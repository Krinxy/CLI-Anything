"""cli-anything-discord - CLI harness for Discord (bot REST API + webhooks)."""

import json
import shlex
import sys

import click
import requests

from cli_anything.discord.core import account as account_core
from cli_anything.discord.core import channels as channels_core
from cli_anything.discord.core import guilds as guilds_core
from cli_anything.discord.core import messages as messages_core
from cli_anything.discord.core import webhooks as webhooks_core
from cli_anything.discord.utils.discord_backend import DiscordClient
from cli_anything.discord.utils.repl_skin import ReplSkin

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}
VERSION = "1.0.0"


def make_client(ctx: click.Context) -> DiscordClient:
    # Token comes from DISCORD_BOT_TOKEN only; there is deliberately no --token flag
    # (argv ends up in shell history and process listings).
    return DiscordClient()


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
    """cli-anything-discord - control Discord from the command line.

    Auth: set DISCORD_BOT_TOKEN (bot commands) or DISCORD_WEBHOOK_URL (webhook send).
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
    skin = ReplSkin("discord", version=VERSION)
    skin.print_banner()
    pt_session = skin.create_prompt_session()

    while True:
        try:
            line = skin.get_input(pt_session, project_name="discord")
        except (EOFError, KeyboardInterrupt):
            break

        line = line.strip()
        if not line:
            continue
        if line in ("exit", "quit"):
            break
        if line == "help":
            skin.help({
                "whoami": "Show the bot account (validates the token)",
                "guild list/info": "Guilds the bot is in",
                "channel list/info": "Channels in a guild",
                "message send/history/delete": "Read and write messages",
                "webhook send": "Send via DISCORD_WEBHOOK_URL",
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
    """Show the bot account (validates the token)."""
    data = account_core.whoami(make_client(ctx))
    output({k: data.get(k) for k in ("id", "username", "bot")}, ctx.obj["as_json"])


# ---------------------------------------------------------------------------
# guild
# ---------------------------------------------------------------------------

@cli.group()
def guild():
    """Guilds (servers) the bot is a member of."""


@guild.command("list")
@click.option("--limit", default=100, show_default=True, type=click.IntRange(1, 200))
@click.pass_context
def guild_list(ctx: click.Context, limit: int):
    """List guilds."""
    data = guilds_core.list_guilds(make_client(ctx), limit)
    output([{"id": g["id"], "name": g["name"]} for g in data], ctx.obj["as_json"])


@guild.command("info")
@click.argument("guild_id")
@click.pass_context
def guild_info(ctx: click.Context, guild_id: str):
    """Show one guild."""
    g = guilds_core.get_guild(make_client(ctx), guild_id)
    output({k: g.get(k) for k in ("id", "name", "owner_id", "approximate_member_count",
                                  "approximate_presence_count")}, ctx.obj["as_json"])


# ---------------------------------------------------------------------------
# channel
# ---------------------------------------------------------------------------

@cli.group()
def channel():
    """Channels inside a guild."""


@channel.command("list")
@click.argument("guild_id")
@click.pass_context
def channel_list(ctx: click.Context, guild_id: str):
    """List channels of a guild."""
    output(channels_core.list_channels(make_client(ctx), guild_id), ctx.obj["as_json"])


@channel.command("info")
@click.argument("channel_id")
@click.pass_context
def channel_info(ctx: click.Context, channel_id: str):
    """Show one channel."""
    c = channels_core.get_channel(make_client(ctx), channel_id)
    output({k: c.get(k) for k in ("id", "name", "type", "guild_id", "topic")}, ctx.obj["as_json"])


# ---------------------------------------------------------------------------
# message
# ---------------------------------------------------------------------------

MENTIONS_HELP = "Allow @everyone/@role/@user pings (suppressed by default)"


@cli.group()
def message():
    """Send, read and delete messages."""


@message.command("send")
@click.argument("channel_id")
@click.argument("text")
@click.option("--allow-mentions", is_flag=True, default=False, help=MENTIONS_HELP)
@click.pass_context
def message_send(ctx: click.Context, channel_id: str, text: str, allow_mentions: bool):
    """Send TEXT to a channel (max 2000 characters)."""
    m = messages_core.send_message(make_client(ctx), channel_id, text, allow_mentions)
    output({"id": m["id"], "channel_id": m["channel_id"]}, ctx.obj["as_json"])


@message.command("history")
@click.argument("channel_id")
@click.option("--limit", default=20, show_default=True, type=click.IntRange(1, 100))
@click.option("--before", default=None, help="Only messages before this message ID")
@click.pass_context
def message_history(ctx: click.Context, channel_id: str, limit: int, before: str | None):
    """Show recent messages, newest first.

    Content is empty unless the bot has the MESSAGE_CONTENT privileged intent enabled.
    """
    output(messages_core.get_history(make_client(ctx), channel_id, limit, before), ctx.obj["as_json"])


@message.command("delete")
@click.argument("channel_id")
@click.argument("message_id")
@click.pass_context
def message_delete(ctx: click.Context, channel_id: str, message_id: str):
    """Delete a message (the bot needs Manage Messages for other people's)."""
    output(messages_core.delete_message(make_client(ctx), channel_id, message_id), ctx.obj["as_json"])


# ---------------------------------------------------------------------------
# webhook
# ---------------------------------------------------------------------------

@cli.group()
def webhook():
    """Send through a channel webhook (no bot needed)."""


@webhook.command("send")
@click.argument("text")
@click.option("--username", default=None, help="Override the webhook's display name")
@click.option("--allow-mentions", is_flag=True, default=False, help=MENTIONS_HELP)
@click.pass_context
def webhook_send(ctx: click.Context, text: str, username: str | None, allow_mentions: bool):
    """Send TEXT using the webhook in DISCORD_WEBHOOK_URL."""
    m = webhooks_core.send_webhook(text, username, allow_mentions=allow_mentions)
    output({"id": m.get("id"), "channel_id": m.get("channel_id")}, ctx.obj["as_json"])


if __name__ == "__main__":
    main()
