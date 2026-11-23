# Discord - CLI Harness SOP

## Overview

Discord exposes a REST API (v10) for bots and per-channel webhooks.

**Real software:** the live Discord HTTP API (not a binary to invoke).
**CLI role:** build validated requests - call the real API - return structured results.

## Architecture

- **API base:** `https://discord.com/api/v10/`
- **Bot auth:** `Authorization: Bot <token>`, token from `DISCORD_BOT_TOKEN` only
- **Webhook auth:** the URL itself is the credential, from `DISCORD_WEBHOOK_URL` only
- **HTTP client:** `requests`. No `discord.py` / gateway: this CLI is one-shot REST, so a websocket stack adds weight for no gain.

## Command groups

| Group | Endpoints |
|-------|-----------|
| `whoami` | `GET /users/@me` |
| `guild list/info` | `GET /users/@me/guilds`, `GET /guilds/{id}` |
| `channel list/info` | `GET /guilds/{id}/channels`, `GET /channels/{id}` |
| `message send/history/delete` | `POST/GET /channels/{id}/messages`, `DELETE /channels/{id}/messages/{id}` |
| `webhook send` | `POST <webhook url>?wait=true` |

Every command supports `--json`. Running with no subcommand starts the REPL.

## Safety rules (enforced in code, covered by tests)

- No `--token` flag: argv leaks into shell history and process lists. Tokens and webhook URLs never appear in output or errors.
- IDs must be numeric snowflakes before they are placed in a URL path (blocks `../` path tricks).
- Webhook URLs must be `https://<discord host>/api/webhooks/...`, so the credential cannot be sent to another server. URLs with userinfo, a backslash, a non-443 port, a query string or a fragment are refused, and the path must be exactly `/api/webhooks/<numeric id>/<token>` (no `..`), the URL must name the same host for urlparse and for the parser inside requests (urllib3), and redirects are never followed.
- `allowed_mentions` is `{"parse": []}` by default, so an agent cannot ping `@everyone`. Opt in with `--allow-mentions`.
- A 429 is reported with `retry_after`; it is never retried in a loop.
- A non-JSON answer (for example an HTML page from a proxy) is an error, never returned as data.
- Content is limited to 2000 characters client-side.

## Known limits

- `message history` returns empty `content` unless the bot has the **MESSAGE_CONTENT** privileged intent (Developer Portal -> Bot).
- No gateway: no live events, presence or voice. Out of scope for a one-shot CLI.
- Selfbots / user tokens are intentionally unsupported (against Discord's Terms of Service).
