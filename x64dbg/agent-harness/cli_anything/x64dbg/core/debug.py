"""Debugging workflows on top of an x64dbg session."""

from cli_anything.x64dbg.utils.x64dbg_backend import X64dbgSession

REGISTERS = ("rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp", "rip",
             "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15", "eflags")
X32_REGISTERS = ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp", "esp", "eip", "eflags")


def read_registers(session: X64dbgSession, arch: str = "x64", timeout: float = 30) -> dict:
    """Read the general-purpose registers as {name: hex string}."""
    names = REGISTERS if arch == "x64" else X32_REGISTERS
    fmt = " ".join(f"{n}={{x:{n}}}" for n in names)
    result = session.run(f'log "{fmt}"', timeout)
    line = next((ln for ln in result["output"] if ln.startswith(f"{names[0]}=")), "")
    return dict(pair.split("=", 1) for pair in line.split() if "=" in pair)


def run_commands(session: X64dbgSession, commands: list, timeout: float = 30) -> list:
    return [session.run(c, timeout) for c in commands]


def debug_target(target: str, commands: list, arch: str = "x64", regs: bool = False,
                 cmd_timeout: float = 30, load_timeout: float = 60) -> dict:
    """Start target under x64dbg, run commands in order, always stop the debuggee. EXECUTES the target."""
    with X64dbgSession(arch) as session:
        session.load(target, load_timeout)
        results = run_commands(session, commands, cmd_timeout)
        out = {"target": target, "arch": arch, "results": results}
        if regs:
            out["registers"] = read_registers(session, arch, cmd_timeout)
        out["state"] = session.state
    return out
