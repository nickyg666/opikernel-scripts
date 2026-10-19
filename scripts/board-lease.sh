#!/bin/bash
# board-lease.sh — single-writer lease for the physical board's POWER + SERIAL.
#
# WHY: two automations were driving the same physical resource. The cron
# group-orchestrator saw "board .151 unreachable" (it has no OS running, so SSH can
# never succeed) and power-cycled the Wyze plug every ~10 min — 190 cycles logged.
# Meanwhile boot pipelines held the serial port and were mid-transfer. Every power cut
# lands in the middle of a transfer or a boot, which is exactly how you get
# "FDT_ERR_BADMAGIC", "board stuck at the U-Boot prompt", and SD-card wear.
#
# SINGLE SOURCE OF TRUTH (2026-09-18): /home/host/opikernel/pvrgl-work/board.lease.json
# That is the file /home/host/smartplug.py enforces. This script used to write a second
# lease (state/board-lease.json) that smartplug never read — split brain: taking the
# "wrong" lease left the power plug still refused. It now reads/writes the same file.
# Schema: {"owner","ts","ttl","host"}  (ttl seconds, expiry = ts + ttl)
#
# Usage:
#   board-lease.sh take <owner> [minutes]   # default 60
#   board-lease.sh release
#   board-lease.sh status
#   board-lease.sh check                    # rc 0 = free (no active lease), 1 = held
#
# The orchestrator calls `check`; while a lease is active it will not touch power
# or serial. Long jobs should `take` for their duration AND export
# BOARD_LEASE_OWNER=<owner> so smartplug.py accepts their power ops.
set -u
LEASE="${BOARD_LEASE:-/home/host/opikernel/pvrgl-work/board.lease.json}"
mkdir -p "$(dirname "$LEASE")"

case "${1:-status}" in
  take)
    OWNER="${2:-unknown}"
    MINS="${3:-60}"
    python3 - "$LEASE" "$OWNER" "$MINS" <<'PY'
import json, os, sys, time
p, owner, mins = sys.argv[1], sys.argv[2], int(sys.argv[3])
d = {"owner": owner, "ts": time.time(), "ttl": mins * 60, "host": "168"}
tmp = p + ".tmp"
json.dump(d, open(tmp, "w"))
os.replace(tmp, p)
print(f"LEASE TAKEN by {owner} for {mins}m (until {time.strftime('%H:%M:%S', time.localtime(d['ts'] + d['ttl']))})")
PY
    ;;
  release)
    rm -f "$LEASE" && echo "LEASE RELEASED"
    ;;
  status)
    python3 - "$LEASE" <<'PY'
import json, sys, time
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("no active lease"); raise SystemExit(0)
rem = int(d.get("ts", 0) + d.get("ttl", 0) - time.time())
if rem <= 0:
    print(f"lease EXPIRED (owner {d.get('owner')}, {int(-rem/60)}m ago)")
else:
    print(f"lease ACTIVE: owner={d.get('owner')} expires in {rem//60}m{rem%60}s")
PY
    ;;
  check)
    python3 - "$LEASE" <<'PY'
import json, sys, time
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    raise SystemExit(0)                      # no file -> free
raise SystemExit(0 if d.get("ts", 0) + d.get("ttl", 0) <= time.time() else 1)
PY
    ;;
  *)
    echo "usage: $0 take <owner> [minutes] | release | status | check" >&2
    exit 2
    ;;
esac
