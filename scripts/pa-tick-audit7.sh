#!/bin/bash
K=/home/host/.hermes/kanban.db
DB=/home/host/.hermes-web-ui/hermes-web-ui.db
echo "=== A. kanban: every non-done task, assignee + title (duplicate-work check) ==="
sqlite3 -readonly "$K" "select status||' | '||coalesce(assignee,'-')||' | '||id||' | '||substr(title,1,46) from tasks where status!='done' order by status,assignee;"
echo
echo "=== B. is 'workflow-organizer' a member of ANY room? ==="
sqlite3 -readonly "$DB" "select a.name||' | room='||r.name||' | removed='||coalesce(a.removedAt,0) from gc_room_agents a join gc_rooms r on r.id=a.roomId where a.name like '%roganiz%' or a.name like '%workflow%';"
echo "(empty = no such member anywhere)"
echo
echo "=== C. duplicate agent->task pairs in kanban ==="
sqlite3 -readonly "$K" "select coalesce(assignee,'-')||' -> '||count(*) from tasks where status='in_progress' group by assignee having count(*)>1;"
echo "(empty = one task each)"
echo
echo "=== D. kanban claim leakage: tasks whose assignee is not in KernelDev-GPU ==="
sqlite3 -readonly "$K" "select id||' | '||status||' | '||coalesce(assignee,'-') from tasks where status!='done' and coalesce(assignee,'-') not in (select name from gc_room_agents where roomId='mti5ax1clq0zlx' and removedAt=0);"
