#!/bin/bash
DB=/home/host/.hermes-web-ui/hermes-web-ui.db
cd /home/host/opikernel || exit 1
echo "=== schema: gc_messages / gc_room_agents ==="
sqlite3 -readonly "$DB" "select name||' :: '||group_concat(name,',') from pragma_table_info('gc_messages');" 2>/dev/null
sqlite3 -readonly "$DB" "select name from pragma_table_info('gc_messages');" | tr '\n' ' '; echo
sqlite3 -readonly "$DB" "select name from pragma_table_info('gc_room_agents');" | tr '\n' ' '; echo
sqlite3 -readonly "$DB" "select name from pragma_table_info('gc_rooms');" | tr '\n' ' '; echo
echo
echo "=== orchestrator patch ordering (proc start vs file mtime) ==="
ps -o lstart,etime -p 4065255 | tail -1
ls -l --time-style=+%m-%d_%H:%M:%S scripts/group-orchestrator.sh
echo
echo "=== rooms ==="
sqlite3 -readonly "$DB" "select id||' | '||name from gc_rooms;"
