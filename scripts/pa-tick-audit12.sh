#!/bin/bash
DB=/home/host/.hermes-web-ui/hermes-web-ui.db
R=mti5ax1clq0zlx
echo "=== BL-19 mentions in room log, last 30 min (who claimed?) ==="
sqlite3 -readonly "$DB" "select datetime(CAST(timestamp AS INTEGER)/1000,'unixepoch')||' | '||senderName||' | '||substr(replace(content,char(10),' '),1,180) from gc_messages where roomId='$R' and CAST(timestamp AS INTEGER)>1758357000000 and content like '%BL-19%' and senderName not in ('pa','PA') order by CAST(timestamp AS INTEGER) desc limit 8;"
echo "--- same for BL-13 ---"
sqlite3 -readonly "$DB" "select datetime(CAST(timestamp AS INTEGER)/1000,'unixepoch')||' | '||senderName||' | '||substr(replace(content,char(10),' '),1,140) from gc_messages where roomId='$R' and CAST(timestamp AS INTEGER)>1758357000000 and content like '%BL-13%' and senderName not in ('pa','PA') order by CAST(timestamp AS INTEGER) desc limit 6;"
echo
echo "=== current BL-19 block, raw ==="
sed -n '206,210p' /home/host/opikernel/agentic-pool/BACKLOG.md
echo "=== now ==="; date -u +%H:%M:%SZ
