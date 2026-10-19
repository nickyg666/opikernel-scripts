#!/bin/bash
# PA probe 4: agent connectors vs dispatch. Who is "connected"?
cd /home/host
DB=/home/host/.hermes-web-ui/hermes-web-ui.db
echo "=== gc_agent_connectors schema"; sqlite3 "file:$DB?mode=ro" "pragma table_info(gc_agent_connectors);"
echo "=== all connector rows"; sqlite3 -header -column "file:$DB?mode=ro" "select * from gc_agent_connectors;" | cut -c1-200
echo
echo "=== gc_agent_pairing_requests schema"; sqlite3 "file:$DB?mode=ro" "pragma table_info(gc_agent_pairing_requests);"
echo "=== pairing requests (last 10)"; sqlite3 -header -column "file:$DB?mode=ro" "select * from gc_agent_pairing_requests order by rowid desc limit 10;" | cut -c1-220
