#!/bin/bash
# PA bounded probe: does ANY gc_run session exist for build-engineer / powervr-monkey today?
cd /home/host
echo "=== hermes session/log dirs"
for d in .hermes/sessions .hermes/logs .hermes/state; do
  [ -d "$d" ] && echo "-- $d" && ls -1 "$d" | head -5
done
echo "=== gc_run entries in agent.log (last 40, cut)"
grep -a -o -E 'gc_run_[A-Za-z0-9_-]+' .hermes/logs/agent.log 2>/dev/null | sort | uniq -c | sort -rn | head -20
echo "=== any mention of build-engineer today 17:0-17:45"
grep -a -n 'build-engineer' .hermes/logs/agent.log 2>/dev/null | tail -5 | cut -c1-260
echo "=== powervr-monkey"
grep -a -n 'powervr-monkey' .hermes/logs/agent.log 2>/dev/null | tail -5 | cut -c1-260
