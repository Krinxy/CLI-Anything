# cli-anything-discord

CLI harness for Discord - send messages, read channel history and inspect servers from the command line or via agents.

## Prerequisites

A Discord bot (or just a webhook):

1. Create an application at https://discord.com/developers/applications and add a Bot.
2. Copy the bot token into the environment (never into a file or command line):
   ```bash
   export DISCORD_BOT_TOKEN=...        # PowerShell: $env:DISCORD_BOT_TOKEN = "..."
   ```
3. Invite the bot to your server (OAuth2 URL generator, scope `bot`, with Send Messages / Read Message History).
4. For `message history` to return text, enable the **MESSAGE_CONTENT** intent in the Developer Portal.
5. Webhook-only use: `export DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/<id>/<token>`

## Installation

```bash
cd discord/agent-harness
pip install -e .
cli-anything-discord --help
```

## Usage

```bash
cli-anything-discord                                   # interactive REPL
cli-anything-discord --json whoami
cli-anything-discord --json guild list
cli-anything-discord --json channel list <guild_id>
cli-anything-discord message send <channel_id> "build finished"
cli-anything-discord --json message history <channel_id> --limit 10
cli-anything-discord message delete <channel_id> <message_id>
cli-anything-discord webhook send "deploy ok" --username CI
```

@everyone / @role pings are suppressed unless you pass `--allow-mentions`.

## Tests

```bash
python3 -m pytest cli_anything/discord/tests/ -v
```

Live tests need a throwaway bot and server: set `DISCORD_BOT_TOKEN` and `DISCORD_TEST_CHANNEL_ID`.
