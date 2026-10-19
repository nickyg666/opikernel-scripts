#!/usr/bin/env python3
"""PA 2026-09-20: patch group-orchestrator.sh so its whip stops feeding stuck drain keys.

Atomic: writes /tmp/group-orchestrator.sh.new, syntax-checks it, then os.replace()
over the live script.  The running bash keeps its own (old) inode, so there is no
partial-read hazard; the keepalive cron picks up the patched version on restart.
"""
import hashlib
import os
import py_compile  # noqa: F401  (kept for parity with other patchers)
import subprocess
import sys

SRC = "/home/host/opikernel/scripts/group-orchestrator.sh"
NEW = SRC + ".new-pa"   # must be same filesystem as SRC for an atomic os.replace

A_ANCHOR = '''  done <<< "$STALE"
  STALE="$KEEP"
  STALE_FLAT=$(printf '%s' "$STALE" | tr '\\n' ' ')
'''

A_INSERT = '''
  # --- dead-lane quarantine (2026-09-20, PA) ----------------------------------
  # build-engineer / powervr-monkey / kernel-architect / Backlog-worker2 have 0
  # completed mentions in 3 h while their rows pile up (11+ reaped, 25-54 still
  # queued). Their per-(room,agent) drain key is stuck, so EVERY @mention this
  # tick enqueues a row that is never delivered - measured 25 fresh undelivered
  # rows in the last 30 min, all created by this script's own digest. Keep such
  # lanes in the digest TEXT (visibility + accountability for the human) but out
  # of every STRUCTURED mention, or the whip feeds a black hole and the room
  # reads a stuck drain as laziness. Predicate shared with kernel-room-nudge.sh
  # via scripts/lane-wedge-check.py so the two whip paths cannot disagree.
  WEDGED=$(ROOM_ID="$ROOM" timeout 6 python3 /home/host/opikernel/scripts/lane-wedge-check.py --room "$ROOM" --names-only 2>/dev/null || true)
  lane_wedged() { [ -n "$WEDGED" ] && printf '%s\\n' "$WEDGED" | grep -Fxq -- "$1"; }
  if [ -n "$WEDGED" ]; then
    echo "  [$ROOM] wedged lanes (mentions suppressed): $(printf '%s' "$WEDGED" | tr '\\n' ' ')"
  fi
'''

B_ANCHOR = '''      [ -z "$role" ] && continue
      [ $i -ge 4 ] && break
'''

B_INSERT = '''      if lane_wedged "$role"; then
        echo "  [$ROOM] skip ${role} (lane WEDGED - drain key stuck, mention would be undelivered)"
        continue
      fi
'''

C_ANCHOR = '''        if roster_has "$role"; then
          MARGS+=(--mention "$role")
'''

C_INSERT = '''        if lane_wedged "$role"; then
          # text only - never a structured mention into a stuck drain key
          MTOKENS="${MTOKENS}${role}~(wedged) "
          echo "  [$ROOM] digest: '$role' lane WEDGED - listed as text only, no mention"
          continue
        fi
'''


def main():
    src = open(SRC).read()
    if "lane_wedged" in src:
        print("already patched - refusing to double-apply")
        return 1
    for name, anchor in (("A", A_ANCHOR), ("B", B_ANCHOR), ("C", C_ANCHOR)):
        n = src.count(anchor)
        if n != 1:
            print("anchor %s matched %d times, need exactly 1" % (name, n))
            return 1
    out = src.replace(A_ANCHOR, A_ANCHOR + A_INSERT)
    out = out.replace(B_ANCHOR, B_ANCHOR + B_INSERT)
    out = out.replace(C_ANCHOR, C_INSERT + C_ANCHOR)
    if out.count("lane_wedged") != 3:
        print("unexpected lane_wedged count: %d" % out.count("lane_wedged"))
        return 1
    open(NEW, "w").write(out)
    r = subprocess.run(["bash", "-n", NEW], capture_output=True, text=True)
    if r.returncode != 0:
        print("SYNTAX FAIL (not applied): %s" % r.stderr.strip())
        return 1
    print("bash -n OK, %d -> %d bytes" % (len(src), len(out)))
    os.chmod(NEW, 0o755)
    if os.environ.get("APPLY") != "1":
        print("DRY_RUN (set APPLY=1 to replace)")
        return 0
    os.replace(NEW, SRC)
    d = open(SRC).read()
    print("applied: bytes=%d md5=%s" % (len(d), hashlib.md5(d.encode()).hexdigest()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
