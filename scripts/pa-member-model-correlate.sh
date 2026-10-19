#!/bin/bash
# PA bounded probe 3: correlate room membership provider/model against "has a gc_run session".
cd /home/host
DB=/home/host/.hermes-web-ui/hermes-web-ui.db
echo "=== every member of the kernel room: name | agentId | provider | model | apiMode | removedAt"
sqlite3 -header -column "file:$DB?mode=ro" "select name,agentId,provider,model,apiMode,removedAt from gc_room_agents where roomId='mti5ax1clq0zlx' order by name;"
echo
echo "=== OmniRoute: last 8 call_logs rows (requested_model/status)"
sqlite3 -header -column "file:/var/lib/omniroute/storage.sqlite?mode=ro" \
  "select requested_model,status,substr(coalesce(error,'-'),1,60) err,datetime(created_at,'unixepoch','localtime') at from call_logs order by created_at desc limit 8;" 2>&1
echo
echo "=== OmniRoute combo 'freeAF' hop list"
sqlite3 -header -column "file:/var/lib/omniroute/storage.sqlite?mode=ro" \
  "select name,updated_at,typeof(data) from combos;" 2>&1
