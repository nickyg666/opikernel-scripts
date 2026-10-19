#!/bin/bash
# End-to-end proof: digest @mentions EVERY stale worker, one dispatch each, no double.
cd /home/host/opikernel || exit 1
T0=$(date +%s)
echo "=== stale set at IDLE_MIN=2 (detector re-runs inside the tick) ==="
IDLE_MIN=2 timeout 200 bash scripts/group-orchestrator.sh
echo "rc=$?"
echo
echo "=== this tick in the log ==="
tail -14 logs/group-orchestrator.log
echo
echo "=== queue rows per message created by this tick ==="
sqlite3 -header /home/host/.hermes-web-ui/hermes-web-ui.db \
 "select messageId, count(*) as n_dispatched, group_concat(targetAgentName,' | ') as agents
    from gc_execution_queue
   where roomId='mti5ax1clq0zlx' and createdAt/1000 >= $T0
   group by messageId order by min(createdAt);"
echo
echo "=== the room message(s) ==="
sqlite3 /home/host/.hermes-web-ui/hermes-web-ui.db \
 "select datetime(timestamp/1000,'unixepoch','localtime') || ' | ' || content || ' | mentions=' || mentions
    from gc_messages
   where roomId='mti5ax1clq0zlx' and timestamp/1000 >= $T0 and mentions!='[]'
   order by timestamp;"
