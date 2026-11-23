# Test Plan - cli-anything-discord

## Test Inventory Plan

- `test_core.py`: 52 unit tests (no network, no token: `requests` is mocked)
- `test_full_e2e.py`: 4 subprocess tests against the installed `cli-anything-discord` command, plus 1 live test (skipped unless `DISCORD_BOT_TOKEN` and `DISCORD_TEST_CHANNEL_ID` are set)

## Unit Test Plan (test_core.py)

- **DiscordClient**: token required, `Authorization: Bot` header from env, URL building, empty body, 429 raises `RateLimited` with `retry_after` and is never retried, HTTP error text carries the Discord code but never the token, network errors wrapped
- **Validation**: snowflakes reject `../`, spaces, letters, over-long values; content limit 2000; webhook URLs must be https on a Discord host with an `/api/webhooks/` path (rejects lookalike hosts)
- **Core**: mentions suppressed by default (`allowed_mentions: {parse: []}`), opt-in, bad channel ID fails before any request, history shape and `before`/`limit` params, delete, channel type mapping, guild list/info, webhook send sends no bot auth
- **CLI**: `--json` output for whoami / guild list / message send, `--limit` bounds, no `--token` flag exists, help lists all groups

## E2E Test Plan (test_full_e2e.py)

- Subprocess: `--help`, missing token -> JSON error + exit 1, invalid channel ID rejected before network, non-Discord webhook URL rejected
- Real API without an account (opt-in, `CLI_ANYTHING_NETWORK_TESTS=1`): an invalid token returns 401; a made-up webhook URL returns `Unknown Webhook` (code 10015). Verified against the live Discord API.
- Live (opt-in, throwaway bot + server): whoami -> send -> history contains the message -> delete

## Realistic workflow tested (live)

`whoami` -> `message send <channel> "..."` -> `message history <channel> --limit 5` -> `message delete`.
The live path was not run in CI; run it with your own bot before relying on it.

## Verified against the real API without an account

A real Discord call with an invalid token returns 401 and the harness reports `Discord API error 401` with exit code 1. A made-up webhook URL returns 404 `Unknown Webhook` (code 10015). A send, history or delete with a real bot is still untested.

## Test Results

```
........................................................sss              [100%]
56 passed, 3 skipped in 1.75s
```

With `CLI_ANYTHING_NETWORK_TESTS=1` (real API calls with invalid credentials, no account needed):

```
........................................................s..              [100%]
58 passed, 1 skipped in 3.42s
```
