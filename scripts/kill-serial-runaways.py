#!/usr/bin/env python3
"""Kill runaway serial readers on the board console WITHOUT matching the calling shell.

Pitfall this exists to solve: `pkill -f 'cat /dev/ttyACM0'` matches the invoking
`bash -c "<command>"` cmdline (which contains the same literal text) and SIGTERMs
the caller.  This only kills processes whose *executable* is cat AND whose argv[1]
is one of the known board-console paths, plus their sudo wrappers.

Path note (2026-09-18): the probe re-enumerates (ttyACM0 -> ttyACM1) after a USB
unbind/bind, so matching one literal missed readers on the new node. Match the whole
set: the udev symlink, the compat alias, and any ttyACM* node.
"""
import os
import re
import signal
import sys

TARGET_RE = re.compile(r"^/dev/(opiz3w-serial|ttyACM[0-9]+)$")


def is_target(path):
    return bool(TARGET_RE.match(path))
me = os.getpid()
# walk our own ancestry so we never kill ourselves or our shell
protect = {me}
pid = me
for _ in range(12):
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            ppid = int(f.read().split(b") ", 1)[1].split()[1])
    except Exception:
        break
    protect.add(ppid)
    if ppid <= 1:
        break
    pid = ppid

killed = []
for entry in os.listdir("/proc"):
    if not entry.isdigit():
        continue
    p = int(entry)
    if p in protect:
        continue
    try:
        with open(f"/proc/{p}/cmdline", "rb") as f:
            argv = [a.decode(errors="ignore") for a in f.read().split(b"\x00") if a]
    except Exception:
        continue
    if not argv:
        continue
    exe = os.path.basename(argv[0])
    # case 1: real cat reading the port   -> argv == ['cat', '/dev/ttyACM0' | '/dev/opiz3w-serial']
    is_bare_cat = exe in ("cat", "/bin/cat", "/usr/bin/cat") and any(
        is_target(a) for a in argv[1:]
    ) and len(argv) <= 3
    # case 2: a sudo/pkexec wrapper around that same thing
    is_wrapper = exe == "sudo" and "cat" in argv and any(is_target(a) for a in argv)
    if is_bare_cat or is_wrapper:
        try:
            os.kill(p, signal.SIGKILL)
            killed.append((p, " ".join(argv[:3])))
        except Exception:
            pass

print(f"killed {len(killed)} runaway serial reader(s)")
for p, c in killed[:15]:
    print(f"  pid {p}: {c}")
if len(killed) > 15:
    print(f"  ... +{len(killed) - 15} more")
sys.exit(0)
