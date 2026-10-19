#!/bin/bash
# PA RCA: hung orchestrator + lock inherited by fallback-spawned yolo agents
echo "=== the lock holder ==="
ps -o pid,ppid,etime,stat,wchan:24,lstart,cmd -p 3391610 2>/dev/null
echo "=== its children ==="
pgrep -P 3391610 -a 2>/dev/null | head
echo "=== who else holds the lock fd ==="
fuser /home/host/opikernel/state/group-orchestrator.lock 2>&1 | tr ' ' '\n' | grep -E '^[0-9]+$' | while read p; do
  printf '%s  %s  %s\n' "$p" "$(ps -o etime= -p $p 2>/dev/null | tr -d ' ')" "$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | cut -c1-60)"
done
echo "=== tick outcomes, last 30 === (RAN vs SKIPPED)"
grep -oE 'orchestrator tick \(group\)|tick SKIPPED' /home/host/opikernel/logs/group-orchestrator.log | tail -30 | sort | uniq -c
echo "=== last 8 tick header lines ==="
grep -E 'orchestrator tick' /home/host/opikernel/logs/group-orchestrator.log | tail -8
