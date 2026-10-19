#!/bin/bash
DB=/home/host/.hermes-web-ui/hermes-web-ui.db
R=mti5ax1clq0zlx
echo "=== A. registered agents in KernelDev-GPU ($R) ==="
sqlite3 -readonly "$DB" "select agentId||' | '||coalesce(name,'?')||' | profile='||coalesce(profile,'-')||' | removed='||coalesce(removedAt,'no') from gc_room_agents where roomId='$R' order by name;"
echo
echo "=== B. real last message per sender (UTC) vs orchestrator stale list ==="
sqlite3 -readonly "$DB" "select datetime(max(timestamp)/1000,'unixepoch')||' UTC | '||senderName||' | msgs='||count(*) from gc_messages where roomId='$R' group by senderName order by max(timestamp) desc limit 14;"
echo
echo "=== C. newest 4 messages ==="
sqlite3 -readonly "$DB" "select datetime(timestamp/1000,'unixepoch')||' '||senderName||': '||substr(replace(content,char(10),' '),1,70) from gc_messages where roomId='$R' order by timestamp desc limit 4;"
echo
echo "=== D. who has NOT posted since 03:30 EDT (= 07:30 UTC) ==="
sqlite3 -readonly "$DB" "select senderName||' last='||datetime(max(timestamp)/1000,'unixepoch') from gc_messages where roomId='$R' and senderType='agent' group by senderName having max(timestamp) < 1758353400000 order by max(timestamp);"
echo "--- now ---"; date -u +"%H:%M:%S UTC"
