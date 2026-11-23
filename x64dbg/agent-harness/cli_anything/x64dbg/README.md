# cli-anything-x64dbg

CLI harness for x64dbg - drive the real headless debugger from the command line or via agents: breakpoints, stepping, registers and memory. Windows only. Debugging a target **executes** it.

## Prerequisites

Download a snapshot from https://github.com/x64dbg/x64dbg/releases, unzip it, and point the harness at it:

```powershell
$env:X64DBG_DIR = "C:\path\to\x64dbg"     # the folder that contains 'release'
```

## Installation

```bash
cd x64dbg/agent-harness
pip install -e .
cli-anything-x64dbg --help
```

## Usage

```bash
cli-anything-x64dbg --execute                          # interactive REPL (one persistent session)

# one-shot scripted session; --execute confirms that the target will be run
cli-anything-x64dbg --json run app.exe --execute \
    --cmd "bp kernel32.CreateFileW" --cmd run \
    --cmd 'log "rip={x:rip} rsp={x:rsp}"' \
    --cmd 'log "{mem;20@rsp}"' --regs

cli-anything-x64dbg run app.exe --execute --script steps.txt     # one command per line, # comments
cli-anything-x64dbg --arch x32 run old32.exe --execute --cmd run   # 32-bit target
```

Inside the REPL (needs `--execute` at startup): `load C:\samplespp.exe` (backslashes and spaces are fine), `run`, `sti`, `bp <addr>`, `regs`, `quit`. Lines other than `load` and `regs` go to x64dbg unfiltered. Evaluate with `log "{x:rip}"` (hex sizes in `{mem;SIZE@addr}`).

Use a VM for untrusted samples. x64dbg stores per-target databases in `headless/db` next to `headless.exe`.

## Tests

```bash
python3 -m pytest cli_anything/x64dbg/tests/ -v
```

Unit tests run anywhere against a fake headless. Live tests (real x64dbg on `find.exe`) run only on Windows with `X64DBG_DIR` set.
