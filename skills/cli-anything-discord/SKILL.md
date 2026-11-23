---
name: "cli-anything-discord"
description: >-
  Command-line interface for Discord - send messages, read channel history, list servers and channels, and post via webhooks through the Discord REST API. Designed for AI agents and power users who need to automate Discord without a GUI.
---

# cli-anything-discord

Discord automation via the bot REST API and channel webhooks. Designed for AI agents and power users who need to post updates, read history and inspect servers without a GUI.

## Installation

```bash
pip install git+https://github.com/HKUDS/CLI-Anything.git#subdirectory=discord/agent-harness
```

**Prerequisites:** a Discord bot token in `DISCORD_BOT_TOKEN` (bot commands) and/or a webhook URL in `DISCORD_WEBHOOK_URL`. Secrets are read from the environment only; there is deliberately no `--token` flag. See `cli_anything/discord/README.md` for bot setup.

## Usage

Running with no subcommand starts the REPL. Add `--json` before the command for machine-readable output (errors become `{"error": "..."}` with exit code 1).

```bash
cli-anything-discord --json whoami
cli-anything-discord --json guild list
cli-anything-discord --json channel list <guild_id>
cli-anything-discord --json message send <channel_id> "text"
cli-anything-discord --json message history <channel_id> --limit 20 [--before <message_id>]
cli-anything-discord --json message delete <channel_id> <message_id>
cli-anything-discord --json webhook send "text" [--username NAME]
```

## Command Groups

| Group | Commands | Purpose |
|-------|----------|---------|
| `whoami` | - | Show the bot account; validates the token |
| `guild` | `list`, `info` | Servers the bot is in |
| `channel` | `list`, `info` | Channels of a guild (type, parent) |
| `message` | `send`, `history`, `delete` | Post, read and remove messages |
| `webhook` | `send` | Post through `DISCORD_WEBHOOK_URL`, no bot needed |

## Agent Guidance

- Start with `whoami`, then `guild list` and `channel list <guild_id>` to find numeric IDs. IDs must be digits.
- Pings are suppressed by default; add `--allow-mentions` only when the user asked for a ping.
- Messages are limited to 2000 characters.
- A rate-limit error includes `retry_after` seconds. Wait that long; do not loop.
- `message history` returns empty `content` unless the bot has the MESSAGE_CONTENT intent. Say so instead of guessing.
- Never print, log or store the token or webhook URL.
