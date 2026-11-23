"""Stand-in for x64dbg's headless.exe, mimicking the protocol observed on the real tool.

One command per stdin line; output as text lines; resume commands announce "[STATE] ..." events.
Used by the unit tests so they run anywhere without x64dbg.
"""

import os
import re
import sys
import threading

REGS = {"rax": 0x1300, "rbx": 0, "rcx": 0x41, "rdx": 0x1300, "rsi": 0, "rdi": 0, "rbp": 0, "rsp": 0x4000,
        "rip": 0x1300, "r8": 1, "r9": 2, "r10": 3, "r11": 4, "r12": 0, "r13": 0, "r14": 0, "r15": 0,
        "eflags": 0x202, "eax": 7, "ebx": 0, "ecx": 0, "edx": 0, "esi": 0, "edi": 0, "ebp": 0, "esp": 0x40,
        "eip": 0x1300}
debugging = False


def say(*lines):
    for line in lines:
        print(line, flush=True)


def expand(text):
    return re.sub(r"\{x:(\w+)\}", lambda m: format(REGS[m.group(1)], "X") if m.group(1) in REGS else "???", text)


say("Initializing debugger...", "[headless] entering command loop...")
for raw in sys.stdin:
    cmd = raw.strip()
    word = cmd.split(None, 1)[0].lower() if cmd else ""
    if word == "init":
        path = re.search(r'"(.*)"', cmd).group(1)
        if "bad" in path:
            say("File does not exist!")
        else:
            debugging = True
            say("Debugging: " + path, "[STATE] initialized", "[SYMBOL] [DIA] Skipping non-existent PDB: x.pdb",
                "[STATE] paused", "System breakpoint reached!")
    elif word in ("r", "run", "sti", "sto", "stepover") and not debugging:
        say(f'The command "{cmd}" is debug-only')
    elif word in ("r", "run"):
        REGS["rip"] = 0x1400
        say("[STATE] running", "INT3 breakpoint at entry!", "[STATE] paused", "[STATE] paused")
    elif word in ("sti", "sto", "stepover"):
        REGS["rip"] += 4
        say("[STATE] running", "[STATE] paused", "[STATE] paused")
    elif word == "erun":
        say("[STATE] running")  # never pauses: lets tests exercise the timeout path
    elif word == "rtr":
        say("[STATE] running")  # rtr (a resume command) pauses only after 1s: its event arrives after a short timeout has expired
        threading.Timer(1.0, lambda: say("[STATE] paused")).start()
    elif word == "die":
        sys.exit(3)
    elif word == "log":
        say(expand(re.search(r'"(.*)"', cmd).group(1)))
    elif word == "stop":
        if os.environ.get("FAKE_STOP_FILE"):
            open(os.environ["FAKE_STOP_FILE"], "w").write("stop received")
        debugging = False
        say("[STATE] stopped", "Debugging stopped!")
    else:
        say(f'Unknown command/expression: "{cmd}"')
