#!/bin/bash
# PA bounded action: verify the orchestrator's stale list + kanban dup policing + bridges
DB=$HOME/.hermes-web-ui/hermes-web-ui.db
KB=$HOME/.hermes/kanban.db
NOW=$(date +%s)

echo "=== NOW $(date +%H:%M:%S) ==="
echo "--- live agents + last msg age (room mti5ax1clq0zlx) ---"
sqlite3 -readonly "$DB" "
select a.name,
       datetime(max(m.createdAt)/1000,'unixepoch','localtime') as last,
       cast((strftime('%s','now') - max(m.createdAt)/1000)/60 as int) as age_min
from gc_room_agents a
left join gc_messages m on m.agentId=a.id and m.roomId=a.roomId
where a.roomId='mti5ax1clq0zlx' and a.removedAt=0
group by a.name order by age_min desc;" 2>&1 | head -20

echo "--- stale targets: live-row? ---"
sqlite3 -readonly "$DB" "
select name, case when removedAt=0 then 'LIVE' else 'REMOVED' end
from gc_room_agents where roomId='mti5ax1clq0zlx'
and lower(name) in ('build-engineer','powervr-monkey');" 2>&1 | head

echo "--- kanban in_progress dup check ---"
sqlite3 -readonly "$KB" "
select count(*) as in_progress,
       count(distinct assignee) as distinct_assignees,
       sum(case when claim_expires is null then 1 else 0 end) as no_expiry
from tasks where status='in_progress';" 2>&1
sqlite3 -readonly "$KB" "
select title, assignee, count(*) c from tasks where status='in_progress'
group by title, assignee having c>1;" 2>&1 | head

echo "--- bridges ---"
systemctl is-active group-telegram-bridge ha-webhook-relay hermes-webui 2>&1 | tr '\n' ' '; echo
journalctl -u group-telegram-bridge --since -40min --no-pager 2>/dev/null | grep -cE "tg send failed|can't parse"

echo "--- board/serial ---"
ls -l --time-style=+%m-%d_%H:%M:%S /home/host/opikernel/pvrgl-work/sercap_room_live.log 2>&1
ls -l --time-style=+%m-%d_%H:%M:%S /home/host/opikernel/pvrgl-work/board.lease.json 2>&1
