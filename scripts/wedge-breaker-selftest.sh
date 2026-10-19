#!/bin/bash
# wedge-breaker-selftest.sh — prove BOTH directions of the whip circuit breaker.
#
# WHY: a breaker that only ever fires is as broken as one that never fires. The
# 2026-09-20 regression was the never-fires direction (an uncoalesced SQL NULL came
# back as rc=2, the callers' `|| true` read that as "no wedged lanes", and the whip
# re-mentioned four dead lanes for three ticks). Run this after ANY edit to
# kernel-room-nudge.sh or lane-wedge-check.py.
#
# Expected, per case: rc/model -> decision.
#   real predicate      rc=0 toolok=1  -> TRUST the list   (quarantined=N)
#   exits 2 (db error)  rc=2 toolok=1  -> FAIL CLOSED, reuse last good list
#   syntax-broken file  rc=1 toolok=0  -> FAIL CLOSED, reuse last good list
#   exits 1, valid py   rc=1 toolok=1  -> TRUST, list cleared (un-quarantine works)
#
# Usage: bash scripts/wedge-breaker-selftest.sh
set -uo pipefail
cd /home/host/opikernel || exit 2

printf 'import sys\nsys.exit(2)\n'  > /tmp/wedge-rc2.py
printf 'def f(:\n'                 > /tmp/wedge-broken.py
printf 'import sys\nsys.exit(1)\n' > /tmp/wedge-rc1.py
bash -n scripts/kernel-room-nudge.sh || { echo "FAIL: bash -n"; exit 1; }
echo "bash -n OK"

for T in real /tmp/wedge-rc2.py /tmp/wedge-broken.py /tmp/wedge-rc1.py real; do
  if [ "$T" = real ]; then
    OUT=$(DRY_RUN=1 bash scripts/kernel-room-nudge.sh 2>&1)
  else
    OUT=$(WEDGE_TOOL=$T DRY_RUN=1 bash scripts/kernel-room-nudge.sh 2>&1)
  fi
  Q=$(printf '%s' "$OUT" | grep -ao 'quarantined=[0-9]*' | tail -1)
  W=$(printf '%s' "$OUT" | grep -ac 'WARN: wedge predicate')
  printf '%-24s %-22s warn=%s list_lines=%s\n' "$T" "${Q:-no-decision-line}" "$W" "$(wc -l < state/wedge-last.txt)"
  printf '%s\n' "$OUT" | grep -a 'WARN:' | head -1 | sed 's/^/    /'
done

echo "--- expect: real=quarantined>=1 warn=0 | rc2/broken=reused list warn=1 | rc1=quarantined=0 warn=0 | real(last)=quarantined>=1"
