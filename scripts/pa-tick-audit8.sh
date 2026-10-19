#!/bin/bash
K=/home/host/.hermes/kanban.db
DB=/home/host/.hermes-web-ui/hermes-web-ui.db
NOW=$(date -u +%s000)
echo "=== A. kanban tasks schema: is the board room-scoped? ==="
sqlite3 -readonly "$K" "select name from pragma_table_info('tasks');" | tr '\n' ' '; echo
echo "--- any room/board column populated? ---"
sqlite3 -readonly "$K" "select name from pragma_table_info('tasks') where name like '%room%' or name like '%board%' or name like '%workspace%';"
echo "(empty = ONE global board shared by both rooms)"
echo
echo "=== B. Neorunner activity: is 'Workflow organizer' (BL-02 assignee) alive? ==="
sqlite3 -readonly "$DB" "select senderName||' | posts60m='||sum(CAST(timestamp AS INTEGER)>($NOW-3600000))||' | last='||datetime(max(CAST(timestamp AS INTEGER))/1000,'unixepoch') from gc_messages where roomId='mti3yr2g3yjpyr' group by senderName order by max(CAST(timestamp AS INTEGER)) desc limit 8;"
echo
echo "=== C. BL-02 backlog line + blocker text ==="
grep -n '^### BL-02' -A6 /home/host/opikernel/agentic-pool/BACKLOG.md
