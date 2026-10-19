#!/bin/bash
# read-only audit of the auto-nudge + power-cycle loop state
cd /home/host/opikernel

echo "=== power-cycle attempts: last 6 ==="
grep -o 'attempt [0-9]*' logs/group-orchestrator.log | tail -6
echo "total 'attempt N' lines: $(grep -c 'attempt ' logs/group-orchestrator.log)"

echo
echo "=== last power/board lines ==="
grep -n 'lease ACTIVE\|smartplug\|cycling\|board .151' logs/group-orchestrator.log | tail -8

echo
echo "=== lease status ==="
./scripts/board-lease.sh status 2>&1

echo
echo "=== nudge cooldown state ==="
ls -alrt state/ 2>/dev/null | tail -8
for f in state/nudge-state.json state/nudge_state.json state/group-nudge-state.json; do
  [ -f "$f" ] && echo "--- $f ---" && head -c 700 "$f" && echo
done

echo
echo "=== live yolo sessions ==="
pgrep -af 'hermes chat .*--yolo' | wc -l

echo
echo "=== smartplug lease guard proof (last refusal) ==="
grep -rn 'REFUSED' /home/host/opikernel/logs/*.log 2>/dev/null | tail -3
