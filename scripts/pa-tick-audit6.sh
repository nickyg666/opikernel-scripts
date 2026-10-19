#!/bin/bash
DB=/home/host/.hermes-web-ui/hermes-web-ui.db
R=mti5ax1clq0zlx
NOW=$(date -u +%s000)
echo "=== gotcha check: typeof(timestamp) ==="
sqlite3 -readonly "$DB" "select distinct typeof(timestamp) from gc_messages where roomId='$R' limit 3;"
echo "--- so numeric compares are TEXT compares; redoing with CAST ---"
echo
echo "=== B'. billing-relay share, last 60 min (CAST) ==="
sqlite3 -readonly "$DB" "select senderName||' | billing='||sum(content like 'Billing or credits%')||' / total='||count(*) from gc_messages where roomId='$R' and CAST(timestamp AS INTEGER)>($NOW-3600000) group by senderName order by count(*) desc;"
echo
echo "=== A'. raw tool-JSON leak into body text, last 60 min ==="
sqlite3 -readonly "$DB" "select senderName||' | leaks='||count(*) from gc_messages where roomId='$R' and CAST(timestamp AS INTEGER)>($NOW-3600000) and content like '{\"%' group by senderName order by count(*) desc limit 8;"
echo "--- leak totals, ALL time ---"
sqlite3 -readonly "$DB" "select 'leaks='||count(*) from gc_messages where roomId='$R' and content like '{\"%';"
echo
echo "=== D'. empty posts, last 60 min ==="
sqlite3 -readonly "$DB" "select coalesce(nullif(senderName,''),'<null>')||' | empty='||count(*) from gc_messages where roomId='$R' and CAST(timestamp AS INTEGER)>($NOW-3600000) and (content is null or trim(content)='') group by senderName order by count(*) desc limit 8;"
echo
echo "=== E'. total posts last 60 min per sender (silence audit) ==="
sqlite3 -readonly "$DB" "select senderName||' | posts='||count(*)||' | last='||datetime(max(CAST(timestamp AS INTEGER))/1000,'unixepoch') from gc_messages where roomId='$R' and CAST(timestamp AS INTEGER)>($NOW-3600000) group by senderName order by max(CAST(timestamp AS INTEGER)) desc;"
