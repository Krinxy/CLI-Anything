"""Unit tests for cli-anything-x64dbg. Run anywhere: a fake headless stands in for x64dbg."""

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from cli_anything.x64dbg.core import debug
from cli_anything.x64dbg.utils import x64dbg_backend as backend
from cli_anything.x64dbg.utils.x64dbg_backend import (
    X64dbgSession, check_command, check_target, find_headless,
)
from cli_anything.x64dbg import x64dbg_cli
from cli_anything.x64dbg.x64dbg_cli import _safe_streams, cli, load_argument, main, repl_step

FAKE = [sys.executable, str(Path(__file__).with_name("fake_headless.py"))]


@pytest.fixture
def target(tmp_path):
    p = tmp_path / "app.exe"
    p.write_bytes(b"MZ")
    return str(p)


@pytest.fixture
def session():
    with X64dbgSession(command=FAKE) as s:
        yield s


# --- locating headless.exe ------------------------------------------------

def test_not_windows_is_refused():
    with patch.object(backend, "IS_WINDOWS", False):
        with pytest.raises(RuntimeError, match="Windows only"):
            find_headless()


def test_missing_install_env(monkeypatch):
    monkeypatch.delenv("X64DBG_DIR", raising=False)
    with patch.object(backend, "IS_WINDOWS", True):
        with pytest.raises(RuntimeError, match="X64DBG_DIR"):
            find_headless()


def test_unknown_arch():
    with patch.object(backend, "IS_WINDOWS", True):
        with pytest.raises(RuntimeError, match="Unknown arch"):
            find_headless("arm")


@pytest.mark.parametrize("layout", [("release", "x64"), ("x64",), ()])
def test_finds_headless_in_known_layouts(tmp_path, monkeypatch, layout):
    folder = tmp_path.joinpath(*layout)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "headless.exe").write_text("")
    monkeypatch.setenv("X64DBG_DIR", str(tmp_path))
    with patch.object(backend, "IS_WINDOWS", True):
        assert find_headless("x64") == folder / "headless.exe"


def test_headless_not_found_in_install(tmp_path, monkeypatch):
    monkeypatch.setenv("X64DBG_DIR", str(tmp_path))
    with patch.object(backend, "IS_WINDOWS", True):
        with pytest.raises(RuntimeError, match="No headless.exe"):
            find_headless("x32")


# --- input checks ---------------------------------------------------------

@pytest.mark.parametrize("bad", ["", "   ", "bp a\nrun", "bp a\rrun", "bp a\0"])
def test_command_must_be_single_line(bad):
    with pytest.raises(RuntimeError):
        check_command(bad)


def test_command_is_stripped():
    assert check_command("  run  ") == "run"


def test_target_must_exist(tmp_path):
    with pytest.raises(RuntimeError, match="Target not found"):
        check_target(str(tmp_path / "nope.exe"))


def test_target_returns_resolved_path(target):
    assert Path(check_target(target)) == Path(target).resolve()


# --- session protocol -----------------------------------------------------

def test_start_and_close_terminates_process():
    s = X64dbgSession(command=FAKE)
    s.start()
    proc = s._proc
    s.close()
    assert proc.poll() is not None and s._proc is None


def test_load_waits_for_system_breakpoint_and_filters_noise(session, target):
    lines = session.load(target)
    assert any(ln.startswith("System breakpoint reached") for ln in lines)
    assert not any(ln.startswith("[SYMBOL]") for ln in lines)
    assert session.state == "paused"


def test_load_failure_is_reported(session, tmp_path):
    bad = tmp_path / "bad.exe"
    bad.write_bytes(b"MZ")
    with pytest.raises(RuntimeError, match="could not start"):
        session.load(str(bad))


def test_plain_command_uses_sentinel_and_strips_it(session, target):
    session.load(target)
    result = session.run('log "rip={x:rip}"')
    assert result["output"] == ["rip=1300"]
    assert not result["timed_out"] and "CLIAX" not in json.dumps(result)


def test_resume_waits_for_pause_event(session, target):
    session.load(target)
    result = session.run("run")
    assert result["state"] == "paused" and not result["timed_out"]
    assert any("INT3 breakpoint" in ln for ln in result["output"])
    assert session.run('log "{x:rip}"')["output"][-1] == "1400"


def test_stepping_moves_rip(session, target):
    session.load(target)
    session.run("run")
    session.run("sti")
    assert session.run('log "{x:rip}"')["output"][-1] == "1404"


def test_resume_without_debuggee_returns_debug_only_not_timeout(session):
    result = session.run("run", timeout=5)
    assert any("debug-only" in ln for ln in result["output"]) and not result["timed_out"]


def test_command_that_never_pauses_times_out_with_state(session, target):
    session.load(target)
    result = session.run("erun", timeout=0.8)
    assert result["timed_out"] is True and result["state"] == "running"


def test_unknown_command_text_is_returned(session):
    assert "Unknown command" in session.run("frobnicate")["output"][0]


def test_multiline_command_is_refused_before_sending(session):
    with pytest.raises(RuntimeError, match="single line"):
        session.run("run\nstop")


def test_close_sends_stop(target, tmp_path, monkeypatch):
    marker = tmp_path / "stop.txt"
    monkeypatch.setenv("FAKE_STOP_FILE", str(marker))
    s = X64dbgSession(command=FAKE)
    s.start()
    s.load(target)
    s.close()
    assert marker.read_text() == "stop received"


def test_stale_events_after_a_timeout_do_not_end_the_next_command_early(session, target):
    session.load(target)
    assert session.run("rtr", timeout=0.3)["timed_out"] is True
    time.sleep(1.4)  # the late "[STATE] paused" of rtr is now sitting in the queue
    result = session.run("sti", timeout=5)
    assert result["output"] == ["[STATE] running", "[STATE] paused", "[STATE] paused"]
    assert session.run('log "{x:rip}"')["output"] == ["1304"]


def test_process_death_is_a_clean_error_not_a_hang_or_broken_pipe(session, target):
    session.load(target)
    with pytest.raises(RuntimeError, match="exited"):
        session.run("die", timeout=5)
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="not running|exited"):
        session.run("sti", timeout=30)
    assert time.monotonic() - started < 2


def test_start_failures_are_runtime_errors(tmp_path):
    with pytest.raises(RuntimeError, match="Cannot start"):
        X64dbgSession(command=[str(tmp_path / "no-such-headless")]).start()
    with pytest.raises(RuntimeError, match="did not start"):
        X64dbgSession(command=[sys.executable, "-c", "print('hello')"]).start(timeout=1)


# --- core -----------------------------------------------------------------

def test_read_registers_x64(session, target):
    session.load(target)
    regs = debug.read_registers(session)
    assert regs["rip"] == "1300" and regs["eflags"] == "202" and len(regs) == len(debug.REGISTERS)


def test_read_registers_x32(session, target):
    session.load(target)
    regs = debug.read_registers(session, arch="x32")
    assert regs["eip"] == "1300" and "rax" not in regs


def test_debug_target_runs_commands_and_stops(target):
    with patch.object(debug, "X64dbgSession", lambda arch: X64dbgSession(command=FAKE)):
        out = debug.debug_target(target, ["run", "sti"], regs=True, cmd_timeout=5)
    assert [r["command"] for r in out["results"]] == ["run", "sti"]
    assert out["registers"]["rip"] == "1404" and out["state"] == "paused"


# --- CLI ------------------------------------------------------------------

def test_cli_run_requires_execute(target):
    res = CliRunner().invoke(cli, ["run", target], obj={})
    assert isinstance(res.exception, RuntimeError) and "--execute" in str(res.exception)


def test_cli_run_json_and_script_file(target, tmp_path):
    script = tmp_path / "s.txt"
    script.write_text("# comment\n\nrun\nsti\n")
    seen = {}

    def fake_debug(t, commands, arch, regs, cmd_timeout, load_timeout):
        seen.update(commands=commands, arch=arch, regs=regs, cmd_timeout=cmd_timeout)
        return {"target": t, "arch": arch, "results": [], "state": "paused"}

    with patch.object(debug, "debug_target", fake_debug):
        res = CliRunner().invoke(
            cli, ["--json", "--arch", "x32", "run", target, "--execute", "--cmd", "bp x", "--script", str(script),
                  "--regs", "--timeout", "7"], obj={})
    assert res.exit_code == 0 and json.loads(res.output)["state"] == "paused"
    assert seen == {"commands": ["bp x", "run", "sti"], "arch": "x32", "regs": True, "cmd_timeout": 7}


def test_cli_text_output_lists_commands_and_registers(target):
    data = {"target": target, "arch": "x64", "state": "paused", "registers": {"rip": "1400"},
            "results": [{"command": "run", "output": ["INT3 breakpoint"], "state": "paused", "timed_out": False},
                        {"command": "erun", "output": [], "state": "running", "timed_out": True}]}
    with patch.object(debug, "debug_target", return_value=data):
        out = CliRunner().invoke(cli, ["run", target, "--execute"], obj={}).output
    assert "> run" in out and "INT3 breakpoint" in out and "timed out" in out and "rip=1400" in out


def test_cli_timeout_bounds(target):
    assert CliRunner().invoke(cli, ["run", target, "--execute", "--timeout", "0"], obj={}).exit_code == 2


def test_cli_help_lists_run():
    out = CliRunner().invoke(cli, ["--help"]).output
    assert "run" in out and "--arch" in out


# --- REPL -----------------------------------------------------------------

@pytest.mark.parametrize("line,expected", [
    (r"load C:	ools.exe", r"C:	ools.exe"),
    (r'load "C:\my tools.exe"', r"C:\my tools.exe"),
    ("load   /tmp/a.exe  ", "/tmp/a.exe"),
    ("load", ""),
])
def test_load_argument_keeps_windows_backslashes(line, expected):
    assert load_argument(line) == expected


@pytest.fixture
def fake_session(monkeypatch):
    monkeypatch.setattr(x64dbg_cli, "X64dbgSession", lambda arch: X64dbgSession(command=FAKE))


def test_repl_refuses_without_execute(fake_session):
    state = {}
    with pytest.raises(RuntimeError, match="--execute"):
        repl_step(state, "run", "x64", execute=False)
    assert "session" not in state  # nothing was started


def test_repl_load_run_regs_and_close(fake_session, target):
    state = {}
    try:
        assert repl_step(state, f'load "{target}"', "x64", True) == ["Stopped at the system breakpoint."]
        assert any("INT3 breakpoint" in ln for ln in repl_step(state, "run", "x64", True))
        assert "rip=1400" in repl_step(state, "regs", "x64", True)[0]
        assert "Unknown command" in repl_step(state, "frobnicate", "x64", True)[0]
    finally:
        state["session"].close()


def test_repl_retries_after_a_failed_start(monkeypatch, target):
    attempts = []

    def factory(arch):
        attempts.append(arch)
        return X64dbgSession(command=[sys.executable, "-c", "print('x')"] if len(attempts) == 1 else FAKE)

    monkeypatch.setattr(x64dbg_cli, "X64dbgSession", factory)
    monkeypatch.setattr(X64dbgSession, "start", _slow_fail_once(X64dbgSession.start))
    state = {}
    with pytest.raises(RuntimeError, match="did not start"):
        repl_step(state, f"load {target}", "x64", True)
    assert "session" not in state
    try:
        assert repl_step(state, f"load {target}", "x64", True) == ["Stopped at the system breakpoint."]
    finally:
        state["session"].close()


def _slow_fail_once(real_start):
    def start(self, timeout=30):
        return real_start(self, timeout=1)
    return start


def test_cli_execute_at_root_enables_run(target):
    seen = {}

    def fake_debug(t, commands, arch, regs, cmd_timeout, load_timeout):
        seen["ok"] = True
        return {"target": t, "arch": arch, "results": [], "state": "paused"}

    with patch.object(debug, "debug_target", fake_debug):
        res = CliRunner().invoke(cli, ["--json", "--execute", "run", target], obj={})
    assert res.exit_code == 0 and seen["ok"]


# --- error contract of main() --------------------------------------------

def run_main(monkeypatch, capsys, *argv):
    monkeypatch.setattr(sys, "argv", ["cli-anything-x64dbg", *argv])
    with pytest.raises(SystemExit) as exc:
        main()
    out = capsys.readouterr()
    return exc.value.code, out.out, out.err


def test_usage_error_in_json_mode_is_json_with_exit_2(monkeypatch, capsys):
    code, out, err = run_main(monkeypatch, capsys, "--json", "run")
    assert code == 2 and err == ""
    assert "TARGET" in json.loads(out)["error"]


def test_usage_error_without_json_stays_click_text_on_stderr(monkeypatch, capsys):
    code, out, err = run_main(monkeypatch, capsys, "run")
    assert code == 2 and out == "" and "Usage:" in err and "TARGET" in err


def test_help_exits_zero_with_text(monkeypatch, capsys):
    code, out, _ = run_main(monkeypatch, capsys, "--help")
    assert code == 0 and "run" in out


def test_backend_error_is_json_with_exit_1(monkeypatch, capsys, target):
    with patch.object(debug, "debug_target", side_effect=RuntimeError("no x64dbg here")):
        code, out, _ = run_main(monkeypatch, capsys, "--json", "run", target, "--execute")
    assert code == 1 and json.loads(out) == {"error": "no x64dbg here"}


@pytest.mark.parametrize("flag", [["--json"], []])
def test_unexpected_exception_is_a_message_not_a_traceback(monkeypatch, capsys, target, flag):
    with patch.object(debug, "debug_target", side_effect=KeyError("rip")):
        code, out, err = run_main(monkeypatch, capsys, *flag, "run", target, "--execute")
    text = json.loads(out)["error"] if flag else err
    assert code == 1 and "Unexpected error (KeyError)" in text and "Traceback" not in out + err


def test_abort_in_json_mode_is_json(monkeypatch, capsys):
    import click
    with patch.object(x64dbg_cli, "cli", side_effect=click.Abort()):
        code, out, _ = run_main(monkeypatch, capsys, "--json", "run", "x.exe")
    assert code == 1 and json.loads(out) == {"error": "Aborted."}


def test_non_ascii_output_never_crashes_on_a_legacy_console(monkeypatch):
    import io
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", stream)
    _safe_streams()
    print("module \u4e2d\u6587 caf\u00e9")
    stream.flush()
    assert (chr(92) + "u4e2d").encode() in raw.getvalue() and "caf".encode() in raw.getvalue()
