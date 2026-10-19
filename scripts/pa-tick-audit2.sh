#!/bin/bash
# PA tick audit 2: kanban<->backlog cross-check + room membership vs assignees + real silence per agent
DB=/home/host/.hermes-web-ui/hermes-web-ui.db
K=/home/host/.hermes/kanban.db
cd /home/host/opikernel || exit 1
echo "=== A. backlog status of the 4 non-PA kanban in_progress tasks ==="
for n in 01 02 03 04 14 16; do
  printf 'BL-%s: ' "$n"
  awk -v t="### BL-$n" 'index($0,t)==1{f=1} f&&/^status:/{print $0; exit}' agentic-pool/BACKLOG.md
done
echo "--- claimed-by lines ---"
grep -n 'claimed-by:' agentic-pool/BACKLOG.md | head -12
echo
echo "=== B. room membership vs kanban assignees ==="
sqlite3 -readonly "$DB" "select room_id,count(*) from gc_room_agents group by room_id;"
echo "--- agents in room mti5ax1clq0zlx ---"
sqlite3 -readonly "$DB" "select a.agent_id,coalesce(m.name,'?') from gc_room_agents a left join gc_agent_connectors m on m.id=a.agent_id where a.room_id='mti5ax1clq0zlx';" 2>/dev/null | head -20
echo
echo "=== C. real last-message time per sender, room mti5ax1clq0zlx (epoch ms -> UTC) ==="
sqlite3 -readonly "$DB" "select sender_name||' | '||count(*)||' | '||datetime(max(created_at)/1000,'unixepoch')||' UTC' from gc_messages where room_id='mti5ax1clq0zlx' group by sender_name order by max(created_at) desc limit 15;"
echo "--- newest 3 messages in room ---"
sqlite3 -readonly "$DB" "select datetime(created_at/1000,'unixepoch')||' '||sender_name||': '||substr(replace(content,char(10),' '),1,60) from gc_messages where room_id='mti5ax1clq0zlx' order by created_at desc limit 3;"
echo
echo "=== D. is the orchestrator still ticking? ==="
date -u +"now=%H:%M:%S UTC"
ps -o pid,etime,stat,args -p 4065255 2>/dev/null | tail -2
ls -l --time-style=+%m-%d_%H:%M:%S agentic-pool/orchestrator*.json 2>/dev/null
ls -1t agentic-pool/*.log* agentic-pool/_* 2>/dev/null | head -6
