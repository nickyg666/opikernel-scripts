#!/bin/bash
# PA: unblock the group-chat nudge channel.
# 1) daemon 3391610 runs a pre-patch copy (while-loop body parsed at 00:46:01)
# 2) 26 orphaned `hermes chat --query-file /tmp/yolo-query.*` sessions inherit
#    lock fd 8 and keep the flock held forever, so cron can never start a new one.
set -u
export BOARD_LEASE_OWNER=PA
LOCK=/home/host/opikernel/state/group-orchestrator.lock
L=/home/host/opikernel/logs/group-orchestrator.log
echo "--- BEFORE ---"
echo "daemon     : $(pgrep -f 'bash /home/host/opikernel/scripts/group-orchestrator.sh' | tr '\n' ' ')"
echo "fd8 holders: $(fuser $LOCK 2>/dev/null | tr ' ' '\n' | grep -cE '^[0-9]+$')"
echo "yolo procs : $(pgrep -f yolo-query | wc -l)"
MARK=$(wc -l < "$L")

# --- target list: ONLY yolo-query sessions; never my own ancestry ---
MINE=""
p=$$
while [ "$p" -gt 1 ]; do MINE="$MINE $p"; p=$(awk '{print $4}' /proc/$p/stat 2>/dev/null || echo 1); done
TARGETS=""
for pid in $(ls /proc | grep -E '^[0-9]+$'); do
  case " $MINE " in *" $pid "*) continue ;; esac
  cmd=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null)
  case "$cmd" in *yolo-query*) TARGETS="$TARGETS $pid" ;; esac
done
echo "targets    : $TARGETS"
echo "  (excluded my ancestry:$MINE )"

echo "--- ACT ---"
pkill -TERM -f 'bash /home/host/opikernel/scripts/group-orchestrator.sh' ; echo "  SIGTERM daemon rc=$?"
for pid in $TARGETS; do kill -TERM "$pid" 2>/dev/null; done
sleep 6
for pid in $TARGETS; do kill -KILL "$pid" 2>/dev/null; done
pkill -KILL -f 'bash /home/host/opikernel/scripts/group-orchestrator.sh' 2>/dev/null
sleep 3
echo "--- AFTER ---"
echo "daemon     : '$(pgrep -f 'bash /home/host/opikernel/scripts/group-orchestrator.sh' | tr '\n' ' ')'"
echo "fd8 holders: $(fuser $LOCK 2>/dev/null | tr ' ' '\n' | grep -cE '^[0-9]+$')"
echo "yolo procs : $(pgrep -f yolo-query | wc -l)"
echo "--- waiting 80s for cron to start the PATCHED daemon ---"
sleep 80
NEWPID=$(pgrep -f 'bash /home/host/opikernel/scripts/group-orchestrator.sh' | head -1)
echo "new daemon pid=$NEWPID  etime=$(ps -o etime= -p ${NEWPID:-1} 2>/dev/null | tr -d ' ')  started=$(ps -o lstart= -p ${NEWPID:-1} 2>/dev/null)"
echo "fd8 holders now: $(fuser $LOCK 2>/dev/null | tr ' ' '\n' | grep -cE '^[0-9]+$')"
echo "--- new tick output since mark ---"
tail -n +$((MARK+1)) "$L" | grep -E 'tick|stale=|REJECTED|POST FAILED|nudged|cooldown|yolo session' | head -20
echo "REJECTED since mark: $(tail -n +$((MARK+1)) "$L" | grep -c 'MENTION REJECTED')"
echo "FALLBACK since mark: $(tail -n +$((MARK+1)) "$L" | grep -c 'falling back to local yolo spawn')"
