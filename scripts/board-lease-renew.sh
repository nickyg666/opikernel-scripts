#!/bin/bash
# board-lease-renew.sh — keep the board POWER+SERIAL lease from silently lapsing.
#
# WHY: the lease is written with a ttl (default 60 min). Nothing renewed it, so on
# 2026-09-19 23:26 the TelegramRunner lease expired — and unleased power cycles began
# 6 minutes later (23:32). `smartplug.py` only refuses while a lease is *live*, so an
# expired lease silently re-opened the plug to every agent: 6 anonymous cycles before
# 01:08, each one flapping the card while a boot was in flight.
#
# RULE: renew only when the lease is missing, expired, or already ours. Never steal a
# live lease from another owner (Nick or a long job) — that is the whole point.
#
# Usage: board-lease-renew.sh [minutes]   (default 1440 = 24h)
set -u
LEASE="${BOARD_LEASE:-/home/host/opikernel/pvrgl-work/board.lease.json}"
MINS="${1:-1440}"
OURS="${BOARD_LEASE_OWNER:-TelegramRunner}"
LEASE_SH="${BOARD_LEASE_SH:-/home/host/opikernel/scripts/board-lease.sh}"

python3 - "$LEASE" "$MINS" "$OURS" "$LEASE_SH" <<'PY'
import json, os, subprocess, sys, time

path, mins, ours, lease_sh = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
try:
    d = json.load(open(path))
except Exception:
    d = None

if d:
    left = d.get("ts", 0) + d.get("ttl", 0) - time.time()
    if d.get("owner") != ours and left > 0:
        print("HOLD: live lease owned by %s (%.0fs left) — not stealing" % (d.get("owner"), left))
        raise SystemExit(0)
    print("renew: owner=%s left=%.0fs" % (d.get("owner"), left))
else:
    print("renew: no lease file")

subprocess.run([lease_sh, "take", ours, str(mins)], check=True)
PY
