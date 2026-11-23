"""cli-anything-x64dbg - CLI harness for x64dbg (real headless debugger, Windows)."""

import json
import sys
from pathlib import Path

import click

from cli_anything.x64dbg.core import debug as debug_core
from cli_anything.x64dbg.utils.repl_skin import ReplSkin
from cli_anything.x64dbg.utils.x64dbg_backend import ARCHES, X64dbgSession

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}
VERSION = "1.0.0"
EXECUTE_WARNING = (
    "This starts the target under the debugger, which EXECUTES it. "
    "Pass --execute to confirm (use a VM for untrusted samples)."
)


def output(data, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(data, indent=2, default=str))
        return
    for item in data.get("results", []):
        click.echo(f"> {item['command']}")
        for line in item["output"]:
            click.echo(f"  {line}")
        if item["timed_out"]:
            click.echo("  (timed out; debuggee state: " + item["state"] + ")")
    if "registers" in data:
        click.echo("registers: " + " ".join(f"{k}={v}" for k, v in data["registers"].items()))
    click.echo(f"state: {data['state']}")


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------

@click.group(context_settings=CONTEXT_SETTINGS, invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.option("--arch", type=click.Choice(ARCHES), default="x64", show_default=True,
              help="x64 for 64-bit targets, x32 for 32-bit targets")
@click.option("--execute", "root_execute", is_flag=True, default=False,
              help="Confirm that targets will be executed (needed for the REPL; `run` also accepts it)")
@click.pass_context
def cli(ctx: click.Context, as_json: bool, arch: str, root_execute: bool):
    """cli-anything-x64dbg - drive the real x64dbg headless debugger (Windows only).

    Needs an unzipped x64dbg snapshot (set X64DBG_DIR). Debugging a target executes it.
    """
    ctx.ensure_object(dict)
    ctx.obj.update(as_json=as_json, arch=arch, execute=root_execute)
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


def main():
    try:
        cli(obj={})
    except RuntimeError as exc:
        # Backend failures arrive as exceptions; surface them as parsable JSON with --json.
        # sys.argv is used because the Click context is already unwound here.
        if "--json" in sys.argv:
            click.echo(json.dumps({"error": str(exc)}, default=str))
        else:
            click.echo(str(exc), err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# REPL (one persistent debugger session)
# ---------------------------------------------------------------------------

def load_argument(line: str) -> str:
    """The target of a REPL `load` line. Not shlex: POSIX splitting eats the backslashes of Windows paths."""
    return line[len("load"):].strip().strip('"')


def repl_step(state: dict, line: str, arch: str, execute: bool) -> list:
    """Run one REPL line against the (lazily started) session; returns the lines to print.

    Raises RuntimeError for anything the user should see as an error. `state` holds the session.
    """
    if not execute:
        raise RuntimeError(
            "The REPL starts a debugger, and debugging executes targets. Restart with: cli-anything-x64dbg --execute")
    session = state.get("session")
    if session is None:
        candidate = X64dbgSession(arch)
        candidate.start()  # kept out of `state` until it started, so a failed start is retried next line
        state["session"] = session = candidate
    if line.split(None, 1)[0] == "load":
        session.load(load_argument(line))
        return ["Stopped at the system breakpoint."]
    if line == "regs":
        return ["registers: " + " ".join(f"{k}={v}" for k, v in debug_core.read_registers(session, arch).items())]
    result = session.run(line)
    return result["output"] + ([f"(no completion event; state: {result['state']})"] if result["timed_out"] else [])


@cli.command(hidden=True)
@click.pass_context
def repl(ctx: click.Context):
    """Interactive REPL: one debugger session, raw x64dbg commands. Needs --execute at startup."""
    skin = ReplSkin("x64dbg", version=VERSION)
    skin.print_banner()
    pt_session = skin.create_prompt_session()
    state: dict = {}

    try:
        while True:
            try:
                line = skin.get_input(pt_session, project_name="x64dbg")
            except (EOFError, KeyboardInterrupt):
                break
            line = line.strip()
            if not line:
                continue
            if line in ("exit", "quit"):
                break
            if line == "help":
                skin.help({
                    "load TARGET": "Start TARGET under the debugger (executes it) and stop at the system breakpoint",
                    "regs": "General-purpose registers",
                    "run / sti / sto / bp ADDR / ...": "Any x64dbg command (unrestricted); evaluate with: log \"{x:rip}\"",
                    "quit": "Stop the debuggee and leave",
                })
                continue
            try:
                for out_line in repl_step(state, line, ctx.obj["arch"], ctx.obj["execute"]):
                    click.echo(out_line)
            except RuntimeError as e:
                skin.error(str(e))
    finally:
        if state.get("session") is not None:
            state["session"].close()
    skin.print_goodbye()


# ---------------------------------------------------------------------------
# run (one-shot scripted session)
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("target", type=click.Path(dir_okay=False))
@click.option("--execute", is_flag=True, default=False, help="Confirm that TARGET will be executed")
@click.option("--cmd", "commands", multiple=True, help="x64dbg command to run after the system breakpoint (repeatable)")
@click.option("--script", "script_path", type=click.Path(exists=True, dir_okay=False), default=None,
              help="File with one x64dbg command per line (# comments allowed)")
@click.option("--regs", is_flag=True, default=False, help="Also read the general-purpose registers at the end")
@click.option("--timeout", "cmd_timeout", default=30, show_default=True, type=click.IntRange(1, 3600),
              help="Seconds to wait for each command")
@click.option("--load-timeout", default=60, show_default=True, type=click.IntRange(1, 3600))
@click.pass_context
def run(ctx: click.Context, target: str, execute: bool, commands, script_path, regs: bool,
        cmd_timeout: int, load_timeout: int):
    """Start TARGET under x64dbg, run the commands in order, then stop the debuggee.

    Example: run app.exe --execute --cmd "bp kernel32.CreateFileW" --cmd run --regs
    """
    if not (execute or ctx.obj["execute"]):
        raise RuntimeError(EXECUTE_WARNING)
    all_commands = list(commands)
    if script_path:
        for raw in Path(script_path).read_text(encoding="utf-8").splitlines():
            if raw.strip() and not raw.strip().startswith("#"):
                all_commands.append(raw.strip())
    output(debug_core.debug_target(target, all_commands, ctx.obj["arch"], regs, cmd_timeout, load_timeout),
           ctx.obj["as_json"])


if __name__ == "__main__":
    main()
