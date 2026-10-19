#!/bin/bash
# PA verify: cross-room mention leak fixed? one tick after the patch
S=/home/host/opikernel/scripts/group-orchestrator.sh
L=/home/host/opikernel/logs/group-orchestrator.log
bash -n "$S" && echo "syntax: OK  md5=$(md5sum $S | cut -d' ' -f1)"
MARK=$(wc -l < "$L")
echo "log mark = line $MARK ; waiting 75s for the next tick..."
sleep 75
echo "--- new tick output since mark ---"
tail -n +$((MARK+1)) "$L" | grep -E 'orchestrator tick|stale=|REJECTED|POST FAILED|nudged|cooldown|digest' | head -25
echo "--- counts since mark ---"
NEW=$(tail -n +$((MARK+1)) "$L")
echo "MENTION REJECTED: $(printf '%s' "$NEW" | grep -c 'MENTION REJECTED')"
echo "POST FAILED     : $(printf '%s' "$NEW" | grep -c 'falling back to local yolo spawn')"
