#!/usr/bin/env python3
"""Propagate the stable console path /dev/opiz3w-serial into the LIVE script set.

Scope decision (2026-09-18): 421 files in this repo contain a literal /dev/ttyACM0,
most of them dead one-off boot experiments. Rewriting all of them is churn that the
next new script re-introduces. So:
  * live set below  -> rewritten to the udev symlink (canonical going forward)
  * entire long tail -> covered by /usr/local/bin/opiz3w-serial-compat.sh, which keeps
                        /dev/ttyACM0 valid as an alias whatever the enumeration is.

Backups: <file>.bak-presymlink-20260918 (never overwritten).
"""
import os
import shutil
import sys

OLD = "/dev/ttyACM0"
NEW = "/dev/opiz3w-serial"
BACKUP_SUFFIX = ".bak-presymlink-20260918"

LIVE = [
    "pvrgl-work/pipeline4.py",
    "pvrgl-work/pipeline4b.py",
    "pvrgl-work/pipeline6_earlycon.py",
    "pvrgl-work/pipeline7_bootonly.py",
    "pvrgl-work/pipeline7_bootscr.py",
    "pvrgl-work/pipeline8_bootscr.py",
    "pvrgl-work/manual_boot_earlycon.py",
    "pvrgl-work/keeper_ctl.py",
    "pvrgl-work/control.py",
    "pvrgl-work/sercmd.py",
    "pvrgl-work/ymodem_deploy.py",
    "pvrgl-work/boot_attempt.sh",
    "pvrgl-work/boot_and_capture.sh",
    "pvrgl-work/capture_serial.sh",
    "pvrgl-work/poke_board.sh",
    "scripts/clean_capture_cycle.sh",
    "scripts/serial_only_cycle.sh",
    "scripts/serial_catch_uboot.sh",
    "scripts/serial_capture.py",
    # already symlink-aware, but keep the alias out of new code paths entirely
    "scripts/claim-serial-port.sh",
]

root = "/home/host/opikernel"
changed = []
skipped = []
for rel in LIVE:
    path = os.path.join(root, rel)
    if not os.path.exists(path):
        skipped.append((rel, "missing"))
        continue
    with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
        src = f.read()
    if OLD not in src:
        skipped.append((rel, "no literal"))
        continue
    bak = path + BACKUP_SUFFIX
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
    out = src.replace(OLD, NEW)
    if out == src:
        skipped.append((rel, "unchanged"))
        continue
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(out)
    changed.append((rel, src.count(OLD)))

print(f"rewrote {len(changed)} file(s):")
for rel, n in changed:
    print(f"  {rel}  ({n} occurrence{'s' if n != 1 else ''})")
if skipped:
    print(f"skipped {len(skipped)}:")
    for rel, why in skipped:
        print(f"  {rel}  ({why})")

# syntax gate on every rewritten python file -- a bad sed here costs a boot cycle
fail = 0
for rel, _ in changed:
    if not rel.endswith(".py"):
        continue
    path = os.path.join(root, rel)
    rc = os.system(f"python3 -m py_compile {path!r} >/dev/null 2>&1")
    if rc != 0:
        print(f"  !! SYNTAX FAIL {rel}")
        fail += 1
print("syntax gate:", "FAIL" if fail else "PASS")
sys.exit(1 if fail else 0)
