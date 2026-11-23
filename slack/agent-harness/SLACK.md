# Slack - CLI Harness SOP

## Overview

Slack exposes the Web API (methods like `chat.postMessage`) for apps with a bot token, and incoming webhooks for one-way posting.

**Real software:** the live Slack Web API (not a binary to invoke).
**CLI role:** build validated requests - call the real API - return structured results.

## Architecture

- **API base:** `https://slack.com/api/<method>`
- **Bot auth:** `Authorization: Bearer xoxb-...`, token from `SLACK_BOT_TOKEN` only
- **Webhook auth:** the URL itself is the credential, from `SLACK_WEBHOOK_URL` only
- **HTTP client:** `requests`. One-shot REST only; no Socket Mode / RTM, so no websocket stack.
- **Errors:** Slack mostly answers HTTP 200 with `{"ok": false, "error": "..."}`, so every response is checked for `ok`.

## Command groups

| Group | Methods |
|-------|---------|
| `whoami` | `auth.test` |
| `channel list/info` | `conversations.list`, `conversations.info` |
| `message send/history/delete` | `chat.postMessage`, `conversations.history`, `chat.delete` |
| `webhook send` | `POST <webhook url>` |

Every command supports `--json`. Running with no subcommand starts the REPL.

## Required bot scopes

`chat:write` (send/delete own), `channels:read` (list/info public), `channels:history` (history public). Private channels additionally need `groups:read` / `groups:history`. The bot must be a member of a channel to read or post to it (`/invite @bot`).

## Safety rules (enforced in code, covered by tests)

- No `--token` flag: argv leaks into shell history and process lists. Tokens and webhook URLs never appear in output or errors.
- Channel IDs (`C...`, `G...`, `D...`) and message `ts` values are validated before they are sent; `#names` are rejected.
- Webhook URLs must be `https://hooks.slack.com/services/...`, so the credential cannot be sent to another server. URLs with userinfo, a backslash, a non-443 port, a query string or a fragment are refused, and the path must be exactly three alphanumeric segments (no `..`), the URL must name the same host for urlparse and for the parser inside requests (urllib3), and redirects are never followed.
- Broadcast mentions (`<!channel>`, `<!here>`, `<!everyone>`, `<!subteam^...>`) are broken with a zero-width space by default, so an agent cannot ping a workspace. Opt in with `--allow-mentions`. A single `<@USERID>` mention is left intact.
- A 429 is reported with the `Retry-After` value; it is never retried in a loop.
- A webhook answer other than exactly `ok` is an error, never a success-shaped result.

## Known limits

- No live events (Socket Mode, RTM) and no file uploads: out of scope for a one-shot CLI.
- Bot tokens only. User tokens (`xoxp-`) and browser-session tokens are intentionally not documented or supported.
- Messages are capped at 40,000 characters by Slack; Slack recommends staying under 4,000.
