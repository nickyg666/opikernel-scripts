#!/bin/bash
# PA: the REAL pin for the orchestrator's stale threshold is the out-of-repo
# launcher /usr/local/bin/trigger_agent_updates.sh, which hard-exports
# IDLE_MIN=15 / BLOCK_AGE_MIN=10 and execs the orchestrator. The repo script's
# own default is overridden by that env, so a room quiet 8-14 min yields
# stale=[default] (a UI placeholder, dropped) and ZERO nudges while the room
# watchdog fires at ~7 min. Rewrite the launcher to 7/6, restart the daemon,
# then prove the daemon's own tick prints idle_min 7.
set -u
L=/usr/local/bin/trigger_agent_updates.sh
LOG=/home/host/opikernel/logs/group-orchestrator.log
BAK=/home/host/opikernel/backups/trigger_agent_updates.sh.bak-pa-$(date +%Y%m%d-%H%M%S)
mkdir -p /home/host/opikernel/backups
echo "=== launcher before: $(md5sum "$L" | cut -c1-32)"
cp -a "$L" "$BAK" && echo "backup: $BAK"
python3 - "$L" <<'PY'
import sys, re
p = sys.argv[1]
s = open(p).read()
s2 = re.sub(r'^export IDLE_MIN=.*$', 'export IDLE_MIN="${IDLE_MIN:-7}"', s, flags=re.M)
s2 = re.sub(r'^export BLOCK_AGE_MIN=.*$', 'export BLOCK_AGE_MIN="${BLOCK_AGE_MIN:-6}"', s2, flags=re.M)
open(p, 'w').write(s2)
PY
echo "=== launcher after: $(md5sum "$L" | cut -c1-32)"; grep -n 'IDLE_MIN\|BLOCK_AGE' "$L"
echo "=== who schedules it:"; grep -rns 'trigger_agent_updates' /etc/cron.d /etc/crontab /var/spool/cron/crontabs/root 2>/dev/null | head -4
CUR=$(fuser /home/host/opikernel/state/group-orchestrator.lock 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+$' | while read -r p; do
        c=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null); case "$c" in *group-orchestrator.sh*) echo "$p";; esac; done | head -1)
echo "=== current lock-holding daemon: ${CUR:-none} ($(ps -o lstart= -p "${CUR:-1}" | tr -s ' '))"
[ -n "$CUR" ] && kill -KILL "$CUR" && echo "killed $CUR"
echo "=== waiting 95s for cron to relaunch with IDLE_MIN=7"
sleep 95
NEW=$(pgrep -f 'bash /home/host/opikernel/scripts/group-orchestrator.sh' | head -1)
echo "new daemon=$NEW start=$(ps -o lstart= -p "${NEW:-1}" | tr -s ' ')"
echo "its exec env: $(tr '\0' '\n' < /proc/${NEW:-1}/environ 2>/dev/null | grep -E '^(IDLE_MIN|BLOCK_AGE_MIN)=' | tr '\n' ' ')"
echo "=== log: last tick marker + idle_min"
grep -n 'orchestrator tick (group)' "$LOG" | tail -1
awk -v n="$(grep -n 'orchestrator tick (group)' "$LOG" | tail -1 | cut -d: -f1)" 'NR>=n' "$LOG" | grep -E 'idle_min|block_age_min|stale=' | head -6
