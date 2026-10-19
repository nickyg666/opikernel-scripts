
import sqlite3, time
DB="/home/host/.hermes-web-ui/hermes-web-ui.db"
con=sqlite3.connect("file:%s?mode=ro"%DB, uri=True); c=con.cursor()
def q(s,p=()): return [r for r in c.execute(s,p)]
NM=int(time.time()*1000)
EL=("role IN ('user','assistant') AND TRIM(content) <> '' AND COALESCE(tool_name,'') = '' "
    "AND COALESCE(tool_call_id,'') = '' AND COALESCE(tool_calls,'[]') IN ('','[]') "
    "AND COALESCE(finish_reason,'') NOT IN ('tool_calls','streaming')")
print("== ELIGIBLE per room (server dies >=10001; guard trims at 9000) ==")
for r in q("select roomId,count(*) from gc_messages where "+EL+" group by 1 order by 2 desc"): print(r)
print("== REAPS in LAST 10 MIN (the guard's own cycle): mention still in history? ==")
for r in q("""select q.roomId,case when m.id is null then 'msgGONE' else 'msgLIVE' end m2,count(*)
from gc_execution_queue q left join gc_messages m on m.id=q.messageId
where q.status='failed' and q.lastError='undelivered_reaped_by_room_guard' and q.finishedAt>? group by 1,2""",(NM-600000,)): print(r)
print("== by agent 3h: msgLIVE reaped vs completed ==")
for r in q("""select q.targetAgentName,q.status,count(*),sum(case when m.id is null then 1 else 0 end) gone
from gc_execution_queue q left join gc_messages m on m.id=q.messageId
where q.createdAt>? group by 1,2 order by 1,2""",(NM-3*3600*1000,)): print(r)
print("== 1810 dump: 27 rows, do their mentions still exist? ==")
for r in q("""select case when m.id is null then 'GONE' else 'LIVE' end m2,count(*)
from gc_execution_queue q left join gc_messages m on m.id=q.messageId
where q.id in (select id from gc_execution_queue where status='failed'
 and lastError='undelivered_reaped_by_room_guard' and finishedAt>? limit 40) group by 1""",(NM-3600000,)): print(r)
