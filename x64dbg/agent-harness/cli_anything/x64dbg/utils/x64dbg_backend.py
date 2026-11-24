"""x64dbg backend - drives the real headless.exe over stdin/stdout.

headless.exe ships in the x64dbg snapshot (release/x64 and release/x32). It runs
x64dbg's command loop without the GUI: one command per stdin line, results as
text lines on stdout. Debugger events are announced as "[STATE] paused|running|stopped".

Security notes:
- Starting a target under a debugger EXECUTES it. Callers must opt in explicitly;
  use a VM for untrusted samples.
- No shell is involved (list-form Popen on headless.exe, not a .bat).
- A command containing a newline or NUL could smuggle a second command, so it is refused.
"""

import os
import queue
import subprocess
import threading
import time
import uuid
from pathlib import Path

INSTALL_ENV = "X64DBG_DIR"
IS_WINDOWS = os.name == "nt"
ARCHES = ("x64", "x32")
# Commands that resume the debuggee: completion is the next "[STATE] paused|stopped" event.
RESUME = {"r", "run", "go", "erun", "era", "sti", "stepinto", "sto", "stepover", "rtr", "rtu", "step"}
NOISE_PREFIXES = ("[SYMBOL]",)
STARTED = "entering command loop"
SYSTEM_BP = "System breakpoint reached"
# Lines x64dbg prints when `init` cannot start the target (observed with the 2026.05.27 snapshot). Without them
# load() would wait the whole timeout for a system breakpoint that never comes.
LOAD_FAILURES = ("does not exist", "Use x32dbg", "Use x64dbg", "Invalid PE file")
INSTALL_HELP = (
    f"x64dbg not found. Download a snapshot from https://github.com/x64dbg/x64dbg/releases, unzip it, "
    f"and set {INSTALL_ENV} to the unzipped folder (the one containing 'release'). Windows only."
)


def find_headless(arch: str = "x64") -> Path:
    if not IS_WINDOWS:
        raise RuntimeError("x64dbg runs on Windows only.")
    if arch not in ARCHES:
        raise RuntimeError(f"Unknown arch {arch!r}: use one of {', '.join(ARCHES)}.")
    root = os.environ.get(INSTALL_ENV, "").strip()
    if not root:
        raise RuntimeError(INSTALL_HELP)
    base = Path(root)
    for candidate in (base / "release" / arch / "headless.exe", base / arch / "headless.exe", base / "headless.exe"):
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"No headless.exe for {arch} under {root!r}. " + INSTALL_HELP)


def check_command(command: str) -> str:
    command = command.strip()
    if not command:
        raise RuntimeError("Empty x64dbg command.")
    if any(c in command for c in ("\n", "\r", "\0")):
        raise RuntimeError("An x64dbg command must be a single line (no newline or NUL).")
    return command


def check_target(target: str) -> str:
    path = Path(target).expanduser()
    if not path.is_file():
        raise RuntimeError(f"Target not found: {target}")
    if '"' in str(path):
        raise RuntimeError("Target path must not contain a double quote.")
    return str(path.resolve())


class X64dbgSession:
    """One headless.exe process with a framed command/response interface."""

    def __init__(self, arch: str = "x64", command: list | None = None):
        self.command = command or [str(find_headless(arch))]
        self.cwd = Path(self.command[0]).parent if command is None else None
        self.state = "idle"
        self._lines: queue.Queue = queue.Queue()
        self._proc: subprocess.Popen | None = None
        self._ended = False

    # -- process lifecycle -------------------------------------------------

    def start(self, timeout: float = 30) -> None:
        try:
            self._proc = subprocess.Popen(
                self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                cwd=self.cwd,
            )
        except OSError as e:
            raise RuntimeError(f"Cannot start x64dbg headless ({type(e).__name__}). " + INSTALL_HELP)
        threading.Thread(target=self._pump, daemon=True).start()
        _, ok = self._read_until(lambda ln: STARTED in ln, timeout)
        if not ok:
            self.close()
            raise RuntimeError("x64dbg headless did not start.")

    def close(self) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.poll() is None and self.state != "stopped":
                self._send("stop")
                time.sleep(0.5)
        except (OSError, RuntimeError):
            pass
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
            self._proc = None

    def __enter__(self) -> "X64dbgSession":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- plumbing ----------------------------------------------------------

    def _pump(self) -> None:
        proc = self._proc
        for raw in iter(proc.stdout.readline, b""):
            self._lines.put(raw.decode("utf-8", "replace").rstrip("\r\n"))
        self._lines.put(None)

    def _send(self, text: str) -> None:
        if self._proc is None or self._ended:
            raise RuntimeError("x64dbg headless is not running.")
        try:
            self._proc.stdin.write(text.encode("utf-8") + b"\r\n")
            self._proc.stdin.flush()
        except OSError:
            self._ended = True
            raise RuntimeError("x64dbg headless has exited.")

    def _drain(self) -> None:
        """Discard lines that arrived after the previous command finished or timed out (stale events)."""
        while True:
            try:
                line = self._lines.get_nowait()
            except queue.Empty:
                return
            if line is None:
                self._ended = True
                return
            self._track(line)

    def _read_until(self, matches, timeout: float) -> tuple:
        """Collect lines until matches(line) is true. Returns (lines, matched)."""
        collected, deadline = [], time.monotonic() + timeout
        if self._ended:
            return collected, False
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return collected, False
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty:
                return collected, False
            if line is None:
                self._ended = True
                return collected, False
            self._track(line)
            if not line.startswith(NOISE_PREFIXES):
                collected.append(line)
            if matches(line):
                return collected, True

    def _settle(self, quiet: float = 0.3) -> list:
        """Lines that trail the completion event (the debugger announces state twice)."""
        extra = []
        while True:
            try:
                line = self._lines.get(timeout=quiet)
            except queue.Empty:
                return extra
            if line is None:
                return extra
            self._track(line)
            if not line.startswith(NOISE_PREFIXES):
                extra.append(line)

    def _track(self, line: str) -> None:
        if line.startswith("[STATE] "):
            self.state = line[len("[STATE] "):].strip()

    # -- public API --------------------------------------------------------

    def load(self, target: str, timeout: float = 60) -> list:
        """Start target under the debugger and wait for the system breakpoint. EXECUTES the target."""
        path = check_target(target)
        self._drain()
        self._send(f'init "{path}"')
        lines, ok = self._read_until(
            lambda ln: ln.startswith(SYSTEM_BP) or any(m in ln for m in LOAD_FAILURES), timeout)
        if self._ended:
            raise RuntimeError("x64dbg headless exited while starting the target.")
        failed = [ln for ln in lines if any(m in ln for m in LOAD_FAILURES)]
        if failed or not ok:
            detail = " | ".join(ln.strip() for ln in (failed or lines[-3:]) if "headless.exe" not in ln) \
                or "no system breakpoint was reached"
            hint = ""
            if any("Use x32dbg" in ln for ln in failed):
                hint = " Pass --arch x32 for 32-bit targets."
            elif any("Use x64dbg" in ln for ln in failed):
                hint = " Pass --arch x64 (the default) for 64-bit targets."
            raise RuntimeError(f"x64dbg could not start the target: {detail}.{hint}")
        return lines

    def run(self, command: str, timeout: float = 30) -> dict:
        """Send one x64dbg command and return its output lines."""
        command = check_command(command)
        self._drain()
        self._send(command)
        if command.split(None, 1)[0].lower() in RESUME:
            lines, ok = self._read_until(
                lambda ln: ln.startswith(("[STATE] paused", "[STATE] stopped")) or "debug-only" in ln, timeout)
            lines = lines + self._settle() if ok else lines
        else:
            token = f"CLIAX-{uuid.uuid4().hex[:8]}"
            self._send(f'log "{token}"')
            lines, ok = self._read_until(lambda ln: ln == token, timeout)
            lines = [ln for ln in lines if ln != token]
        if self._ended:
            raise RuntimeError("x64dbg headless exited while running " + repr(command) + ".")
        return {"command": command, "output": lines, "state": self.state, "timed_out": not ok}
