---
name: >-
  cli-anything-slack
description: >-
  Command-line interface for Slack - send messages, read channel history, list channels, and post via incoming webhooks through the Slack Web API. Designed for AI agents and power users who need to automate Slack without a GUI.
---

# cli-anything-slack

Slack automation via the bot Web API and incoming webhooks. Designed for AI agents and power users who need to post updates, read history and inspect channels without a GUI.

## Installation

```bash
pip install git+https://github.com/HKUDS/CLI-Anything.git#subdirectory=slack/agent-harness
```

**Prerequisites:** a Slack bot token in `SLACK_BOT_TOKEN` (bot commands) and/or a webhook URL in `SLACK_WEBHOOK_URL`. Secrets are read from the environment only; there is deliberately no `--token` flag. The bot must be invited to each channel it uses. See `cli_anything/slack/README.md` for app setup and scopes.

## Usage

Running with no subcommand starts the REPL. Add `--json` before the command for machine-readable output (errors become `{"error": "..."}` with exit code 1).

```bash
cli-anything-slack --json whoami
cli-anything-slack --json channel list [--private] [--limit N]
cli-anything-slack --json channel info <channel_id>
cli-anything-slack --json message send <channel_id> "text" [--thread <ts>]
cli-anything-slack --json message history <channel_id> --limit 20 [--latest <ts>]
cli-anything-slack --json message delete <channel_id> <ts>
cli-anything-slack --json webhook send "text"
```

## Command Groups

| Group | Commands | Purpose |
|-------|----------|---------|
| `whoami` | - | Show the bot identity; validates the token |
| `channel` | `list`, `info` | Channels visible to the bot |
| `message` | `send`, `history`, `delete` | Post (optionally in a thread), read and remove messages |
| `webhook` | `send` | Post through `SLACK_WEBHOOK_URL`, no bot needed |

## Agent Guidance

- Start with `whoami`, then `channel list` to find channel IDs. Use IDs (`C...`), never `#names`.
- A `not_in_channel` error means the bot must be invited first (`/invite @bot`); a `missing_scope` error names the scope to add.
- Broadcast pings (`<!channel>`, `<!here>`, `<!everyone>`) are disabled by default; add `--allow-mentions` only when the user asked for a ping.
- A rate-limit error includes the `Retry-After` seconds. Wait that long; do not loop.
- `message send` returns `ts`; pass it to `--thread` to reply in a thread or to `delete` to remove the message.
- Never print, log or store the token or webhook URL.
