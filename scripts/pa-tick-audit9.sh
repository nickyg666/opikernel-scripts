#!/bin/bash
DB=/home/host/.hermes-web-ui/hermes-web-ui.db
R=mti5ax1clq0zlx
NOW=$(date -u +%s000)
echo "=== A. what KIND of row are the leak posts? (role/tool_name/senderType) ==="
sqlite3 -readonly "$DB" "select 'role='||coalesce(role,'-')||' tool='||coalesce(tool_name,'-')||' senderType='||coalesce(senderType,'-')||' n='||count(*) from gc_messages where roomId='$R' and CAST(timestamp AS INTEGER)>($NOW-3600000) and content like '{\"%' group by role,tool_name,senderType order by count(*) desc limit 6;"
echo
echo "=== B. leak rows: run_id present? (is it a transcript mirror?) ==="
sqlite3 -readonly "$DB" "select 'run_id_null='||sum(run_id is null)||' run_id_set='||sum(run_id is not null)||' tool_call_id_set='||sum(tool_call_id is not null) from gc_messages where roomId='$R' and CAST(timestamp AS INTEGER)>($NOW-3600000) and content like '{\"%';"
echo
echo "=== C. example leak row (full row, PA) ==="
sqlite3 -readonly "$DB" "select 'role='||coalesce(role,'-')||' | tool='||coalesce(tool_name,'-')||' | finish='||coalesce(finish_reason,'-')||' | body='||substr(content,1,80) from gc_messages where roomId='$R' and senderName='PA' and content like '{\"%' order by CAST(timestamp AS INTEGER) desc limit 2;"
echo
echo "=== D. writers to the room: who owns the API server / posting path ==="
ss -ltnp 2>/dev/null | grep -E ':8648|:3000|:8080' | head -5
pgrep -af 'hermes-web-ui|next-server|node .*server' | head -5
