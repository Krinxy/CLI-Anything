# x64dbg - CLI Harness SOP

## Overview

x64dbg is an open-source Windows debugger for user-mode binaries. Its release ships `headless.exe` (in `release/x64` and `release/x32`), which runs the x64dbg command loop without the GUI.

**Real software:** x64dbg `headless.exe`, driven over stdin/stdout.
**CLI role:** start a headless session - frame each command with a completion marker - return the output lines as JSON.

## Architecture

- **Install:** unzip a snapshot from https://github.com/x64dbg/x64dbg/releases and set `X64DBG_DIR` to the folder containing `release`.
- **Protocol (observed):** one command per stdin line; results as text lines on stdout. The debugger announces `[STATE] paused|running|stopped`, and `init` ends with `System breakpoint reached!`.
- **Framing:** a plain command is followed by `log "CLIAX-<nonce>"`, and output is collected until the nonce comes back. Resume commands (`run`, `sti`, `sto`, `stepover`, `rtr`, ...) complete on the next `[STATE] paused` or `stopped` event instead, because they return before the debuggee actually stops. A command that never completes returns `timed_out: true` with the last known state.
- **Evaluation:** `?` and `calc` are not available in headless. Use `log` with format specifiers: `log "{x:rip}"`, `log "{mem;10@rsp}"` (the size is hex).
- **Session:** one `headless.exe` per `run` (and per REPL). The REPL is the stateful mode; `run` is the one-shot scripted mode.
- **Side effect:** x64dbg writes per-target databases to `headless/db` next to `headless.exe`.

## Command groups

| Command | Purpose |
|---------|---------|
| `run TARGET --execute [--cmd C]... [--script F] [--regs] [--timeout S] [--arch x64\|x32]` | Start under the debugger, run commands in order, always stop the debuggee |
| (REPL, needs root `--execute`) `load TARGET`, `regs`, any x64dbg command | One persistent session; `load` accepts Windows paths with backslashes and spaces |

Every `run` supports `--json`. Running with no subcommand starts the REPL.

## Safety rules (enforced in code, covered by tests)

- **Debugging executes the target.** `run` and the REPL both refuse without an explicit `--execute` (`cli-anything-x64dbg --execute` for the REPL). Use a VM for untrusted samples.
- **Raw x64dbg commands are not filtered.** Once `--execute` is given, `--cmd` strings and REPL lines go to x64dbg as they are (that includes commands that start processes or load libraries). The CLI is not a sandbox.
- No shell is involved: `headless.exe` is started with list-form arguments.
- A command containing a newline or NUL is refused, so one reviewed command cannot smuggle a second.
- The target path must exist and may not contain a double quote.
- The session is always closed (`stop`, then kill) even if a command fails, so no debuggee or headless process is left behind.
- Events that arrive after a command timed out are discarded before the next command, so they cannot end it early. If `headless.exe` dies, the next command fails with a clear error instead of hanging.

## Known limits

- Windows only.
- No disassembly or GUI views: headless exposes the command loop, not the CPU view. Memory and registers are available through `log` format specifiers.
- x64dbg commands are powerful (`loadlib`, scripting). The CLI passes them through; it is not a sandbox.
- Resume commands rely on state events; if a target hangs without pausing, the command times out and the session is stopped at the end.
