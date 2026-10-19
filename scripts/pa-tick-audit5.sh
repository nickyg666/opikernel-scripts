#!/bin/bash
DB=/home/host/.hermes-web-ui/hermes-web-ui.db
R=mti5ax1clq0zlx
echo "=== A. raw tool-result JSON leaking into the room body text ==="
sqlite3 -readonly "$DB" "select senderName||' | '||count(*) from gc_messages where roomId='$R' and (content like '{\"bytes_written\"%' or content like '{\"kind\":\"workspace_diff\"%' or content like '{\"output\"%' or content like '{\"exit_code\"%' or content like '{\"success\"%') group by senderName order by count(*) desc limit 10;"
echo "--- total leak count + window ---"
sqlite3 -readonly "$DB" "select 'leaks='||count(*)||' first='||datetime(min(timestamp)/1000,'unixepoch')||' last='||datetime(max(timestamp)/1000,'unixepoch') from gc_messages where roomId='$R' and content like '{\"%';"
echo
echo "=== B. provider-death relay ratio (last 2h) ==="
sqlite3 -readonly "$DB" "select senderName||' | billing='||sum(content like 'Billing or credits%')||'/'||count(*) from gc_messages where roomId='$R' and timestamp>1758346800000 group by senderName order by count(*) desc limit 10;"
echo
echo "=== C. removed-but-still-posting agents ==="
sqlite3 -readonly "$DB" "select a.name||' | removedAt='||datetime(a.removedAt/1000,'unixepoch')||' | lastMsg='||coalesce((select datetime(max(m.timestamp)/1000,'unixepoch') from gc_messages m where m.roomId='$R' and m.senderName=a.name),'never') from gc_room_agents a where a.roomId='$R' and a.removedAt>0;"
echo
echo "=== D. empty-content posts (attribution breakage) last 2h ==="
sqlite3 -readonly "$DB" "select coalesce(nullif(senderName,''),'<null>')||' | empty='||count(*) from gc_messages where roomId='$R' and timestamp>1758346800000 and (content is null or trim(content)='') group by senderName;"
