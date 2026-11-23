---
name: >-
  cli-anything-x64dbg
description: >-
  Command-line interface for x64dbg - start Windows binaries under the real headless debugger, set breakpoints, step, and read registers and memory as structured output. Designed for AI agents and reverse engineers who need scriptable dynamic analysis without the GUI. Windows only; debugging executes the target.
---

# cli-anything-x64dbg

Dynamic analysis with the real x64dbg `headless.exe`. Designed for AI agents and reverse engineers who need scripted debugging without a GUI. **Debugging executes the target**: use a VM for untrusted samples.

## Installation

```bash
pip install git+https://github.com/HKUDS/CLI-Anything.git#subdirectory=x64dbg/agent-harness
```

**Prerequisites:** Windows, and an unzipped x64dbg snapshot with `X64DBG_DIR` pointing at the folder that contains `release`. See `cli_anything/x64dbg/README.md`.

## Usage

Running with no subcommand starts the REPL (one persistent session) and needs the root `--execute` flag (`cli-anything-x64dbg --execute`). `--json` goes before the command; errors become `{"error": "..."}` with exit code 1.

```bash
cli-anything-x64dbg --json run TARGET --execute [--cmd CMD]... [--script FILE] [--regs] [--timeout SEC] [--load-timeout SEC]
cli-anything-x64dbg --arch x32 run TARGET32 --execute --cmd run
```

REPL: `load TARGET`, `regs`, or any x64dbg command (passed through unfiltered); `quit` stops the debuggee.

## Command Groups

| Command | Purpose |
|---------|---------|
| `run` | Start TARGET, stop at the system breakpoint, run the commands in order, optionally read registers, then always stop |
| REPL | The same commands against one persistent session |

Each result is `{"command", "output": [lines], "state": "paused|running|stopped", "timed_out": bool}`.

## Agent Guidance

- `--execute` is required (for `run`, and at the root for the REPL) and means "run this binary". Do not pass it for a sample the user has not agreed to execute. Raw x64dbg commands are not filtered, so treat them as code execution.
- The target starts paused at the system breakpoint. `run` continues to the entry breakpoint; `sti` / `sto` step into / over; `bp <addr|module.api>` sets a breakpoint.
- Evaluate with `log`, not `?`: `log "rip={x:rip}"`, `log "{mem;20@rsp}"` (size is hex), `log "{x:rax} {x:rcx}"`.
- Resume commands finish when the debuggee pauses; `timed_out: true` with state `running` means it did not pause within `--timeout`.
- Commands are single lines only. Pass `--arch x32` for 32-bit targets.
- No disassembly view is available headlessly; read bytes with `{mem;...}` and decode them yourself or use cli-anything-ghidra.
