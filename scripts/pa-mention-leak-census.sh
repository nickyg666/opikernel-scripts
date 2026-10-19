#!/bin/bash
# PA census: room-crossed mention batch -> MENTION POST FAILED -> yolo fallback spawn
L=/home/host/opikernel/logs/group-orchestrator.log
echo "log=$(ls -l --time-style=+%m-%d_%H:%M:%S $L | awk '{print $6, $7, $8}')  bytes=$(wc -c < $L)"
echo "MENTION REJECTED total: $(grep -c 'MENTION REJECTED' $L)"
echo "FALLBACK SPAWN total  : $(grep -c 'falling back to local yolo spawn' $L)"
echo "--- rejected agent names (count) ---"
grep -o "unknown agent '[^']*'" $L | sort | uniq -c | sort -rn | head
echo "--- last 6 orchestrator ticks ---"
grep -E 'orchestrator tick' $L | tail -6
echo "--- last 8 fallback-spawn lines ---"
grep -n 'falling back to local yolo spawn\|nudged (fallback spawn)' $L | tail -8
echo "--- unknown_role junk files ---"
ls -l --time-style=+%m-%d_%H:%M:%S /home/host/opikernel/agentic-pool/unknown* 2>/dev/null
