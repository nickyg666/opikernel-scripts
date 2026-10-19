#!/bin/bash
# PA: second sweep — clear the last fd8-holding yolo sessions, then let cron
# start the PATCHED daemon and prove the next tick has no cross-room rejects.
set -u
LOCK=/home/host/opikernel/state/group-orchestrator.lock
L=/home/host/opikernel/logs/group-orchestrator.log
MINE=""; p=$$
while [ "$p" -gt 1 ]; do MINE="$MINE $p"; p=$(awk '{print $4}' /proc/$p/stat 2>/dev/null || echo 1); done
echo "holders: $(fuser $LOCK 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+$' | tr '\n' ' ')"
for pid in $(fuser $LOCK 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+$'); do
  case " $MINE " in *" $pid "*) echo "  skip $pid (me)"; continue ;; esac
  cmd=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null)
  role=$(tr '\0' '\n' < /proc/$pid/environ 2>/dev/null | grep '^ROLE=' | head -1)
  case "$cmd" in
    *yolo-query*) echo "  KILL $pid ($role) ${cmd:0:60}"; kill -KILL "$pid" 2>/dev/null ;;
    *) echo "  keep $pid (not a yolo spawn) ${cmd:0:70}" ;;
  esac
done
sleep 3
echo "holders after sweep: $(fuser $LOCK 2>/dev/null | tr ' ' '\n' | grep -cE '^[0-9]+$')"
echo "yolo procs now      : $(pgrep -f yolo-query | wc -l)"
MARK=$(wc -l < "$L")
echo "--- waiting 85s for cron to launch the patched daemon ---"
sleep 85
NEW=$(pgrep -f 'bash /home/host/opikernel/scripts/group-orchestrator.sh' | head -1)
if [ -n "${NEW:-}" ]; then
  echo "daemon pid=$NEW etime=$(ps -o etime= -p $NEW | tr -d ' ') started=$(ps -o lstart= -p $NEW)"
else
  echo "daemon: NONE yet"
fi
echo "fd8 holders: $(fuser $LOCK 2>/dev/null | tr ' ' '\n' | grep -cE '^[0-9]+$')"
echo "--- tick output since mark ---"
tail -n +$((MARK+1)) "$L" | grep -E 'tick|stale=|REJECTED|POST FAILED|nudged|cooldown|yolo session' | head -18
echo "REJECTED since mark: $(tail -n +$((MARK+1)) "$L" | grep -c 'MENTION REJECTED')"
echo "FALLBACK since mark: $(tail -n +$((MARK+1)) "$L" | grep -c 'falling back to local yolo spawn')"
