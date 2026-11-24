"""E2E tests: subprocess tests run the installed `cli-anything-x64dbg` command.

Live tests drive the real x64dbg headless debugger on a Windows system binary and are skipped unless
X64DBG_DIR points at an unzipped x64dbg snapshot (the folder containing 'release') on Windows.
The target is C:\\Windows\\System32\\find.exe, which exits immediately and is harmless.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time

import pytest

LIVE = sys.platform == "win32" and bool(os.environ.get("X64DBG_DIR"))
live = pytest.mark.skipif(not LIVE, reason="needs Windows and X64DBG_DIR (unzipped x64dbg snapshot)")
FIND = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "find.exe")


def _resolve_cli(name="cli-anything-x64dbg"):
    """Installed command if on PATH (or CLI_ANYTHING_FORCE_INSTALLED=1), else python -m."""
    exe = shutil.which(name)
    if exe:
        return [exe]
    if os.environ.get("CLI_ANYTHING_FORCE_INSTALLED"):
        raise RuntimeError(f"{name} not found on PATH")
    return [sys.executable, "-m", "cli_anything.x64dbg"]


def run_cli(*args, env_extra=None, timeout=300):
    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run(_resolve_cli() + list(args), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=timeout)


def test_help():
    res = run_cli("--help")
    assert res.returncode == 0 and "run" in res.stdout


def test_run_requires_execute_flag(tmp_path):
    target = tmp_path / "t.exe"
    target.write_bytes(b"MZ")
    res = run_cli("--json", "run", str(target))
    assert res.returncode == 1 and "--execute" in json.loads(res.stdout)["error"]


@pytest.mark.skipif(sys.platform == "win32", reason="checks the non-Windows refusal")
def test_refuses_on_non_windows(tmp_path):
    target = tmp_path / "t.exe"
    target.write_bytes(b"MZ")
    res = run_cli("--json", "run", str(target), "--execute")
    assert res.returncode == 1 and "Windows only" in json.loads(res.stdout)["error"]


def test_missing_install_dir_json_error(tmp_path):
    target = tmp_path / "t.exe"
    target.write_bytes(b"MZ")
    env = {k: v for k, v in os.environ.items() if k != "X64DBG_DIR"}
    res = subprocess.run(_resolve_cli() + ["--json", "run", str(target), "--execute"],
                         capture_output=True, text=True, env=env, timeout=60)
    assert res.returncode == 1 and json.loads(res.stdout)["error"]


@pytest.fixture(scope="module")
def session_result():
    res = run_cli("--json", "run", FIND, "--execute", "--regs",
                  "--cmd", "run", "--cmd", 'log "rip={x:rip}"', "--cmd", "sti",
                  "--cmd", 'log "rip={x:rip} mem={mem;4@rip}"')
    assert res.returncode == 0, res.stdout + res.stderr
    return json.loads(res.stdout)


@live
def test_live_run_stops_at_entry_breakpoint(session_result):
    first = session_result["results"][0]
    assert first["state"] == "paused" and not first["timed_out"]
    assert any("entry breakpoint" in line for line in first["output"])


@live
def test_live_step_moves_rip_forward(session_result):
    before = next(ln for ln in session_result["results"][1]["output"] if ln.startswith("rip="))
    after = next(ln for ln in session_result["results"][3]["output"] if ln.startswith("rip="))
    a, b = (int(re.search(r"rip=([0-9A-F]+)", x).group(1), 16) for x in (before, after))
    assert 0 < b - a < 16


@live
def test_live_memory_and_registers(session_result):
    last = next(ln for ln in session_result["results"][3]["output"] if "mem=" in ln)
    assert re.search(r"mem=[0-9A-F]{8}$", last)
    regs = session_result["registers"]
    assert regs["rip"] in last and "rsp" in regs and "eflags" in regs


@live
def test_live_missing_target_is_a_clear_error():
    res = run_cli("--json", "run", os.path.join(os.environ.get("TEMP", "."), "no_such_target.exe"), "--execute")
    assert res.returncode == 1 and "Target not found" in json.loads(res.stdout)["error"]


def test_usage_error_in_json_mode_is_json_on_stdout():
    res = run_cli("--json", "run")
    assert res.returncode == 2
    assert "TARGET" in json.loads(res.stdout)["error"]


# --- real failure modes of the real debugger (no mocks) ---------------------

@live
def test_live_32bit_target_in_the_64bit_debugger_fails_fast_with_the_flag_to_use():
    target = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "SysWOW64", "find.exe")
    if not os.path.isfile(target):
        pytest.skip("no 32-bit system binary")
    started = time.monotonic()
    res = run_cli("--json", "run", target, "--execute", "--cmd", "run")
    assert res.returncode == 1 and time.monotonic() - started < 25  # used to wait the whole 60 s load timeout
    assert "Use x32dbg" in json.loads(res.stdout)["error"] and "--arch x32" in json.loads(res.stdout)["error"]


@live
def test_live_32bit_target_works_with_arch_x32():
    target = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "SysWOW64", "find.exe")
    if not os.path.isfile(target):
        pytest.skip("no 32-bit system binary")
    res = run_cli("--json", "--arch", "x32", "run", target, "--execute", "--cmd", "run", "--regs")
    data = json.loads(res.stdout)
    assert res.returncode == 0 and data["state"] == "paused" and "eip" in data["registers"]


@live
def test_live_text_file_as_target_fails_fast_with_invalid_pe(tmp_path):
    target = tmp_path / "notanexe.txt"
    target.write_text("hello")
    started = time.monotonic()
    res = run_cli("--json", "run", str(target), "--execute")
    assert res.returncode == 1 and time.monotonic() - started < 25
    assert "Invalid PE file" in json.loads(res.stdout)["error"]


@live
def test_live_unknown_command_is_reported_not_fatal():
    res = run_cli("--json", "run", FIND, "--execute", "--cmd", "frobnicate")
    data = json.loads(res.stdout)
    assert res.returncode == 0 and any("Unknown command" in line for line in data["results"][0]["output"])


@live
@pytest.mark.parametrize("folder", ["Max Mustermann", "Jürgen Müller", "O'Neil", "name#1", "a,b", "a;b", "a=b",
                                    "名前", "50% off", "a&b", "a$b"])
def test_live_target_path_may_contain_any_characters(tmp_path, folder):
    """The path goes to x64dbg over stdin, not a command line, so no user or folder name can break it."""
    target_dir = tmp_path / folder
    target_dir.mkdir()
    target = target_dir / "find.exe"
    shutil.copyfile(FIND, target)
    res = run_cli("--json", "run", str(target), "--execute", "--cmd", "run")
    data = json.loads(res.stdout)
    assert res.returncode == 0 and data["state"] == "paused", res.stdout
