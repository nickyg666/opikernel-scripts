#!/bin/bash
# PA: is the room-crossed mention leak LIVE or historical?
L=/home/host/opikernel/logs/group-orchestrator.log
echo "=== last 3 REJECTED lines w/ line# ==="
grep -n 'MENTION REJECTED' "$L" | tail -3
echo "=== timestamp of the tick enclosing the LAST rejection ==="
LN=$(grep -n 'MENTION REJECTED' "$L" | tail -1 | cut -d: -f1)
head -n "$LN" "$L" | grep -E 'orchestrator tick' | tail -1
echo "total lines: $(wc -l < $L)  last rejection at line $LN"
echo "=== Neorunner roster (mti3yr2g3yjpyr) ==="
sqlite3 -readonly /home/host/.hermes-web-ui/hermes-web-ui.db "PRAGMA busy_timeout=8000; SELECT name FROM gc_room_agents WHERE roomId='mti3yr2g3yjpyr' AND removedAt=0 ORDER BY name;"
