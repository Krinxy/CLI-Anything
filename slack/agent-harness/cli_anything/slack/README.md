# cli-anything-slack

CLI harness for Slack - send messages, read channel history and post via webhooks from the command line or via agents.

## Prerequisites

A Slack app with a bot token (or just an incoming webhook):

1. Create an app at https://api.slack.com/apps (from scratch) in your workspace.
2. Under *OAuth & Permissions* add bot scopes `chat:write`, `channels:read`, `channels:history` (plus `groups:read`/`groups:history` for private channels).
3. Install the app and copy the *Bot User OAuth Token* into the environment (never into a file or command line):
   ```bash
   export SLACK_BOT_TOKEN=xoxb-...      # PowerShell: $env:SLACK_BOT_TOKEN = "xoxb-..."
   ```
4. Invite the bot to each channel you use: `/invite @yourbot`.
5. Webhook-only use: create an Incoming Webhook and `export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...`

## Installation

```bash
cd slack/agent-harness
pip install -e .
cli-anything-slack --help
```

## Usage

```bash
cli-anything-slack                                     # interactive REPL
cli-anything-slack --json whoami
cli-anything-slack --json channel list [--private]
cli-anything-slack message send <channel_id> "build finished" [--thread <ts>]
cli-anything-slack --json message history <channel_id> --limit 10
cli-anything-slack message delete <channel_id> <ts>
cli-anything-slack webhook send "deploy ok"
```

Channels are addressed by ID (e.g. `C0123456789`), which `channel list` prints. `<!channel>` / `<!here>` pings are disabled unless you pass `--allow-mentions`.

## Tests

```bash
python3 -m pytest cli_anything/slack/tests/ -v
```

Live tests need a throwaway workspace and bot: set `SLACK_BOT_TOKEN` and `SLACK_TEST_CHANNEL_ID`.
