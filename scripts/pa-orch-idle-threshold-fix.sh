#!/bin/bash
# PA: align the orchestrator's stale threshold with the room watchdog.
# Root cause: group_orchestrator_detect.py:182 gates the stale set on IDLE_MIN
# (default 15) while the room watchdog nudges at ~7 min -> a room quiet for
# 8-14 min reports stale=[default] only, 'default' is dropped as a UI
# placeholder, and the daemon emits ZERO nudges. Proven at 02:04-02:12.
set -u
CRON=/etc/crontab
OLD_LINE='*/1 * * * * /home/host/opikernel/scripts/group-orchestrator.sh >/dev/null 2>&1'
NEW_LINE='*/1 * * * * IDLE_MIN=7 BLOCK_AGE_MIN=6 /home/host/opikernel/scripts/group-orchestrator.sh >/dev/null 2>&1'
BAK=/home/host/opikernel/backups/crontab.bak-pa-idle7-$(date +%Y%m%d-%H%M%S)
mkdir -p /home/host/opikernel/backups
cp -a "$CRON" "$BAK" && echo "backup: $BAK ($(wc -c < "$BAK") B)"
grep -qF "$OLD_LINE" "$CRON" || { echo "ABORT: exact orchestrator line not found"; grep -n orchestr "$CRON"; exit 1; }
python3 - "$CRON" "$OLD_LINE" "$NEW_LINE" <<'PY'
import sys
p, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(p).read()
open(p, 'w').write(s.replace(old, new, 1))
PY
echo "--- /etc/crontab orchestrator line now:"; grep -n orchestr "$CRON"
echo "--- restarting daemon so it parses IDLE_MIN=7 (old pid 3952500)"
for pid in 3952500 $(pgrep -f 'sleep 60' || true); do
  case " $pid " in *" $$ "*) continue ;; esac
  [ -d /proc/$pid ] || continue
  kill -KILL "$pid" 2>/dev/null && echo "  killed $pid"
done
echo "holders on lock now: $(fuser /home/host/opikernel/state/group-orchestrator.lock 2>/dev/null | tr ' ' '\n' | grep -cE '^[0-9]+$')"
