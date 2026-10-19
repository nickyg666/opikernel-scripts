#!/usr/bin/env python3
"""PA 2026-09-20: point kernel-room-nudge.sh at the SHARED dead-lane predicate.

Why: the whip carried its own inline copy of the wedged-lane query. That copy had
`sum(lastError LIKE '%reaped%')` uncoalesced -> NULL for any lane whose only rows
are undrained (lastError NULL) -> TypeError -> empty QUARANTINE -> circuit breaker
silently off -> dead lanes get mentioned again. The orchestrator had the same query
through lane-wedge-check.py, so one NULL disabled both whips at once.

Atomic os.replace: bash re-reads a running script from the same inode, so an
in-place edit can hand cron a half-written file.
"""
import hashlib
import os
import pathlib

P = pathlib.Path("/home/host/opikernel/scripts/kernel-room-nudge.sh")
src = P.read_text()
lines = src.split("\n")

start = next(i for i, l in enumerate(lines) if l.startswith("# --- circuit breaker"))
end = next(i for i, l in enumerate(lines) if l.strip() == ")" and i > start and lines[i - 1].strip() == "PY")

new = [
    "# --- circuit breaker: classify dead lanes BEFORE mentioning anyone -------------",
    "# ONE predicate for every whip path: scripts/lane-wedge-check.py (PA, 2026-09-20).",
    "# This block used to be an inline copy of that query; it is GONE on purpose — a",
    "# duplicated predicate is a predicate that drifts, and the copy's uncoalesced",
    "# sum(lastError LIKE '%reaped%') returned NULL for undrained lanes, crashed the",
    "# breaker, and let the dead lanes be mentioned again.",
    "set +e",
    "QUARANTINE=$(ROOM_ID=\"$ROOM\" WEDGE_DB=\"$DB_GC\" WEDGE_WINDOW_MIN=\"$DEAD_WINDOW_MIN\" \\",
    "  WEDGE_MIN_REAPS=\"$DEAD_REAPS\" WEDGE_PILE=\"$GROSS_PILE\" \\",
    "  timeout 10 python3 /home/host/opikernel/scripts/lane-wedge-check.py --room \"$ROOM\" --all 2>/dev/null)",
    "QRC=$?",
    "set -e",
    "if [ \"$QRC\" = \"2\" ]; then",
    "  echo \"[$(date -Is)] WARN: lane-wedge-check db error — circuit breaker DEGRADED\"",
    "fi",
]
out = lines[:start] + new + lines[end + 1:]
new_src = "\n".join(out)
tmp = P.with_suffix(".sh.pa-tmp")
tmp.write_text(new_src)
os.replace(tmp, P)
print("old md5", hashlib.md5(src.encode()).hexdigest())
print("new md5", hashlib.md5(new_src.encode()).hexdigest())
print("bytes", len(src.encode()), "->", len(new_src.encode()))
