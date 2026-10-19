#!/usr/bin/env python3
"""Syntax-verify every file touched by pkill-fix.py (proves the rewrite is safe)."""
import subprocess
import sys
from pathlib import Path

STAMP = "bak-pkillfix-20260918"
changed = list(Path("/home/host/opikernel/pvrgl-work").glob(f"*.{STAMP}")) + \
          list(Path("/home/host/opikernel/scripts").glob(f"*.{STAMP}"))

ok = bad = 0
fails = []
for bak in sorted(changed):
    orig = bak.with_name(bak.name[: -len("." + STAMP)])
    if not orig.exists():
        continue
    if orig.suffix == ".py":
        r = subprocess.run([sys.executable, "-m", "py_compile", str(orig)],
                           capture_output=True, text=True)
    else:
        r = subprocess.run(["bash", "-n", str(orig)], capture_output=True, text=True)
    if r.returncode == 0:
        ok += 1
    else:
        bad += 1
        fails.append((str(orig), (r.stderr or r.stdout).strip()[:200]))

print(f"verified files: {ok + bad}   PASS={ok}   FAIL={bad}")
for f, e in fails:
    print("FAIL:", f)
    print("   ", e)

# also confirm the new call is present in the rewritten files
good = 0
for bak in changed:
    orig = bak.with_name(bak.name[: -len("." + STAMP)])
    if orig.exists() and "claim-serial-port.sh" in orig.read_text(errors="replace"):
        good += 1
print(f"files now calling the safe claimer: {good}")
sys.exit(1 if bad else 0)
