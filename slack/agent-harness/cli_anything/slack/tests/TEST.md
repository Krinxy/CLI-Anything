# Test Plan - cli-anything-slack

## Test Inventory Plan

- `test_core.py`: 67 unit tests (no network, no token: `requests` is mocked)
- `test_full_e2e.py`: 4 subprocess tests against the installed `cli-anything-slack` command, plus 1 live test (skipped unless `SLACK_BOT_TOKEN` and `SLACK_TEST_CHANNEL_ID` are set)

## Unit Test Plan (test_core.py)

- **SlackClient**: token required, `Authorization: Bearer` from env, GET params vs POST JSON, `ok: false` raises with a hint (and the needed scope for `missing_scope`), error text never contains the token, 429 raises `RateLimited` from `Retry-After` and is never retried, HTTP/non-JSON/network errors wrapped
- **Validation**: channel IDs reject `#names`, lowercase, path tricks; message `ts` format; text limit; webhook URLs must be https on `hooks.slack.com` under `/services/` (rejects lookalike hosts)
- **Mentions**: `<!channel>`, `<!here>`, `<!everyone>`, `<!subteam^..>` are broken by default, kept with `--allow-mentions`, single `<@U..>` mention untouched
- **Core**: whoami, channel list (public by default, private opt-in), send (thread, bad channel rejected before any request), history shape/params/bot fallback, delete, webhook send without bot auth
- **CLI**: `--json` for whoami / channel list / message send, `--limit` bounds, no `--token` flag, help lists all groups

## E2E Test Plan (test_full_e2e.py)

- Subprocess: `--help`, missing token -> JSON error + exit 1, invalid channel ID rejected before network, non-Slack webhook URL rejected
- Real API without an account (opt-in, `CLI_ANYTHING_NETWORK_TESTS=1`): an invalid token returns `invalid_auth`; a made-up webhook URL returns a clean 404 error. Verified against the live Slack API.
- Live (opt-in, throwaway workspace + bot): whoami -> send -> history contains the message -> delete

## Realistic workflow tested (live)

`whoami` -> `channel list` -> `message send <channel> "..."` -> `message history <channel> --limit 5` -> `message delete`.
The live path has not been run against a real workspace yet; run it with your own bot before relying on it.

## Verified against the real API without an account

A real Slack call with an invalid token returns HTTP 200 with `{"ok": false, "error": "invalid_auth"}`, which the harness reports as `Slack API error: invalid_auth` with exit code 1. A made-up webhook URL returns 404. A send, history or delete with a real bot is still untested.

## Test Results

```
ss                                                                       [100%]
71 passed, 3 skipped in 1.79s
```

With `CLI_ANYTHING_NETWORK_TESTS=1` (real API calls with invalid credentials, no account needed):

```
..                                                                       [100%]
73 passed, 1 skipped in 3.34s
```
