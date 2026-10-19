#!/bin/bash
# PA bounded probe 2: which agents have EVER had a gc_run session, and are build-engineer /
# powervr-monkey present in the room membership table?
cd /home/host
echo "=== distinct gc_run agent families (all log files)"
cat .hermes/logs/agent.log .hermes/logs/agent.log.1 .hermes/logs/agent.log.2 .hermes/logs/agent.log.3 2>/dev/null \
 | grep -a -o -E 'gc_run_[A-Za-z0-9]+_default_[A-Za-z0-9-]+_' | sed -E 's/^gc_run_[A-Za-z0-9]+_default_//; s/_$//' \
 | sort | uniq -c | sort -rn
echo "=== membership: gc_room_agents columns"
DB=/home/host/.hermes-web-ui/hermes-web-ui.db
sqlite3 "file:$DB?mode=ro" "pragma table_info(gc_room_agents);"
echo "=== memberships for the two silent agents"
sqlite3 -header -column "file:$DB?mode=ro" "select * from gc_room_agents where name like '%build-engineer%' or name like '%powervr-monkey%';"
