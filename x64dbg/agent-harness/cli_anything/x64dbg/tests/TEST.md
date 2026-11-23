# Test Plan - cli-anything-x64dbg

## Test Inventory Plan

- `test_core.py`: 45 unit tests. A fake `headless` (`fake_headless.py`) reproduces the protocol observed on the real tool, so they run anywhere without x64dbg.
- `test_full_e2e.py`: 4 subprocess tests that need no x64dbg (one of them only on non-Windows), plus 4 live tests against the real x64dbg headless debugger (skipped unless on Windows with `X64DBG_DIR` set)

## Unit Test Plan (test_core.py)

- **Locating headless.exe**: Windows-only guard, missing `X64DBG_DIR`, unknown arch, the three known folder layouts, clear error when `headless.exe` is absent
- **Input checks**: a command must be one line (newline, CR and NUL refused), commands are stripped, the target must exist
- **Session protocol**: start/close terminates the process; `load` waits for the system breakpoint, filters `[SYMBOL]` noise and reports a failed start; plain commands are framed with a sentinel that never leaks into the output; resume commands complete on the `[STATE] paused` event; stepping moves `rip`; a resume before any debuggee returns the "debug-only" text instead of timing out; a command that never pauses returns `timed_out` with state `running`; multi-line commands are refused before anything is sent
- **Core**: register dump for x64 and x32, `debug_target` runs the commands in order and stops
- **Robustness**: events left over from a timed-out command are discarded (a test shows the old behavior would return a stale event); a dead `headless.exe` is a clean error, not a hang or a broken pipe; start failures are runtime errors; `close()` really sends `stop`
- **REPL** (`repl_step`, testable without a terminal): refuses without `--execute`; `load` keeps Windows backslashes and quotes; load, run, regs and raw commands work; a failed start is retried on the next line
- **CLI**: `run` refuses without `--execute`, root `--execute` enables `run`, `--json`, script files with comments and blank lines, text output, timeout bounds

## E2E Test Plan (test_full_e2e.py)

- Subprocess, no x64dbg: `--help`, `--execute` is required, non-Windows refusal, missing `X64DBG_DIR` gives a JSON error
- Live on `C:\Windows\System32\find.exe` (harmless, exits immediately): `run` stops at the entry breakpoint, `sti` moves `rip` forward by a few bytes, `log "{mem;4@rip}"` returns 4 bytes of hex that match `rip`, registers include `rip`, `rsp` and `eflags`, and a missing target is a clear error. After the runs no `find.exe` or `headless.exe` process is left behind (checked by hand with `tasklist`).

## Realistic workflow verified by hand

`run find.exe --execute --cmd run --cmd 'log "rip={x:rip}"' --cmd sti --cmd 'log "rip={x:rip} mem={mem;8@rip}"' --regs`: entry breakpoint at `find.OptionalHeader.AddressOfEntryPoint`, `rip` 7FF60A8E1300 -> 7FF60A8E1304 after one step, and the 8 bytes at the new `rip` read back.

## Test Results

With x64dbg 2026.05.27 on Windows (live tests run; 1 test skipped because it checks the non-Windows refusal):

```
...............................................s.....                    [100%]
52 passed, 1 skipped in 18.76s
```

Without x64dbg (live tests skipped):

```
...............................................s.ssss                    [100%]
48 passed, 5 skipped in 16.01s
```
