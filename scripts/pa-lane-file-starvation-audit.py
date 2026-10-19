#!/usr/bin/env python3
"""PA lane-file starvation audit — roster-filtered, exact-name only.

Why this exists: the naive 'find agentic-pool -name "*.md" -size -300c' signal
had a 100% false-positive rate. Evidence notes (EVIDENCE/BLOCKER dumps) and short
handles (py.md, YOLO.md) are legitimately small and are NOT role files, and
agentic-pool/ is shared with the Neorunner room (mti3yr2g3yjpyr) whose lanes are
out of scope for KernelDev-GPU. Naive runs of the size probe caused PA to touch a
file belonging to another room's lane (minecraft-player, live in Neorunner).

Rules enforced here:
  1. Only lanes with removedAt=0 in the TARGET room are audited.
  2. A role file must match the lane name exactly (case/punct-insensitive).
  3. Evidence/blocker/notes files are never flagged (name-pattern exclusion).
  4. Missing role file = STARVED; file <300B = STUB (report, do not mutate).
Never move or delete a panel file: report, then rebuild from measured state.
"""
import argparse
import os
import re
import sqlite3
import sys

DB = "/home/host/.hermes-web-ui/hermes-web-ui.db"
POOL = "/home/host/opikernel/agentic-pool"
ROOM_DEFAULT = "mti5ax1clq0zlx"  # KernelDev-GPU
EXCLUDE = re.compile(
    r"(EVIDENCE|BLOCKER|RCA|NOTES|HANDOFF|REPORT|SUMMARY|SNAPSHOT|README|INDEX)",
    re.I,
)
STUB_BYTES = 300


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", default=ROOM_DEFAULT)
    ap.add_argument("--pool", default=POOL)
    a = ap.parse_args()

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    lanes = [
        r[0]
        for r in con.execute(
            "select name from gc_room_agents where roomId=? and removedAt=0", (a.room,)
        )
    ]

    files = {}
    for f in os.listdir(a.pool):
        if f.endswith(".md") and os.path.isfile(os.path.join(a.pool, f)):
            files.setdefault(norm(f[:-3]), os.path.join(a.pool, f))

    starved, stubs, ok = [], [], []
    for lane in lanes:
        if EXCLUDE.search(lane):
            continue
        p = files.get(norm(lane))
        if not p:
            starved.append(lane)
        elif os.path.getsize(p) < STUB_BYTES:
            stubs.append((lane, os.path.getsize(p), os.path.basename(p)))
        else:
            ok.append(lane)

    orphans = [
        f
        for f in os.listdir(a.pool)
        if f.endswith(".md")
        and not EXCLUDE.search(f)
        and norm(f[:-3]) not in {norm(x) for x in lanes}
        and os.path.basename(os.path.join(a.pool, f))
        != os.path.basename(os.path.join(a.pool, f))
    ]

    print(f"room={a.room} live_lanes={len(lanes)}")
    print(f"OK={len(ok)} stubs={len(stubs)} STARVED={len(starved)}")
    for lane, sz, fn in stubs:
        print(f"  STUB    {lane}  {sz}B  {fn}")
    for lane in starved:
        print(f"  STARVED {lane}  (no role file — nudge has nothing to seed from)")
    if orphans:
        print("non-lane files (informational, never mutate): " + ", ".join(sorted(orphans)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
