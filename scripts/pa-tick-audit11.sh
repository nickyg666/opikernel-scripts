#!/bin/bash
DB=/home/host/.hermes-web-ui/hermes-web-ui.db
R=mti5ax1clq0zlx
echo "=== who claimed BL-13 at ~08:05:20 UTC? (room log, 08:00-08:10) ==="
sqlite3 -readonly "$DB" "select datetime(CAST(timestamp AS INTEGER)/1000,'unixepoch')||' | '||senderName||' | '||substr(replace(content,char(10),' '),1,150) from gc_messages where roomId='$R' and senderName!='the-human' and content like '%BL-13%' and CAST(timestamp AS INTEGER)>(1758355200000) order by CAST(timestamp AS INTEGER) desc limit 6;"
echo
echo "=== BL-19 claims in room log (last 3h) ==="
sqlite3 -readonly "$DB" "select datetime(CAST(timestamp AS INTEGER)/1000,'unixepoch')||' | '||senderName||' | '||substr(replace(content,char(10),' '),1,140) from gc_messages where roomId='$R' and senderName!='the-human' and content like '%BL-19%' and CAST(timestamp AS INTEGER)>(1758345000000) order by CAST(timestamp AS INTEGER) desc limit 6;"
echo
echo "=== my own earlier audit's verdict lines on BL-13/BL-19 ==="
grep -n 'BL-19\|BL-13' /home/host/opikernel/agentic-pool/PA-EVIDENCE-20260920-0314-crossroom-claim-leak.md | head -12
