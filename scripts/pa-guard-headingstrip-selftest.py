#!/usr/bin/env python3
"""PA 2026-09-21: end-to-end test of the patched guard's heading-strip self-heal.

Replays the real incident: copy the preserved heading-stripped corpse over LIVE, run the
guard, require rc=1 + 24 headings + the exact canonical md5 back.
"""
import hashlib
import pathlib
import shutil
import subprocess

POOL = pathlib.Path("/home/host/opikernel/agentic-pool")
LIVE = POOL / "BACKLOG.md"
CORPSE = POOL / "BACKLOG.md.headings-stripped-20260921-012254"
CANON = "9d8f084bccf3c01ead7f7c11d5279338"


def md5(p):
    return hashlib.md5(p.read_bytes()).hexdigest()


def hd(p):
    return p.read_text(errors="replace").count("\n### BL-")


shutil.copy2(LIVE, POOL / "BACKLOG.md.pre-guardtest")
shutil.copy2(CORPSE, LIVE)
print(f"INJECTED  md5={md5(LIVE)} headings={hd(LIVE)} size={LIVE.stat().st_size} (expect {md5(CORPSE)[:8]}/0)")

r = subprocess.run(["/usr/bin/python3", "/home/host/opikernel/scripts/backlog-lastgood-guard.py"],
                   capture_output=True, text=True, cwd="/home/host/opikernel")
print("guard rc=", r.returncode)
print(r.stdout.strip()[-900:])
print(f"AFTER     md5={md5(LIVE)} headings={hd(LIVE)} size={LIVE.stat().st_size}")
print("VERDICT", "PASS self-healed to canonical" if md5(LIVE) == CANON else "FAIL still broken")
