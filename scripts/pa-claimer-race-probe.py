
import sqlite3, time
DB="/home/host/.hermes-web-ui/hermes-web-ui.db"
con=sqlite3.connect("file:%s?mode=ro"%DB, uri=True); c=con.cursor()
def q(s,p=()): return [r for r in c.execute(s,p)]
NM=int(time.time()*1000); W=NM-3*3600*1000; NS=int(time.time()); WS=NS-3*3600
print("== T0 units: boundary rows ==")
for r in q("select createdAt,typeof(createdAt),status from gc_execution_queue order by createdAt desc limit 3"): print("newest",r)
for r in q("select count(*) from gc_execution_queue where createdAt<100000000000"): print("second-unit rows:",r)
for r in q("select count(*) from gc_execution_queue where createdAt>100000000000"): print("ms-unit rows:",r)
print("== A: stalled pair 3h(ms) status x startedAt ==")
for r in q("""select targetAgentName,status,case when startedAt is null then 'NULL' else 'set' end k,count(*),
round((?-min(createdAt))/60000.0,1) oldest_min from gc_execution_queue where createdAt>?
and targetAgentName in ('build-engineer','powervr-monkey') group by 1,2,3 order by 4 desc""",(NM,W)): print(r)
print("== B: room-wide 3h(ms) ==")
for r in q("select status,case when startedAt is null then 'NULL' else 'set' end k,count(*) from gc_execution_queue where createdAt>? group by 1,2",(W,)): print(r)
print("== C: failed lastError 3h ==")
for r in q("select substr(coalesce(lastError,'<none>'),1,55) e,count(*) from gc_execution_queue where createdAt>? and status='failed' group by e order by 2 desc limit 8",(W,)): print(r)
print("== D: startedAt-NULL 3h by finishedAt/msg ==")
for r in q("""select q.status,case when q.finishedAt is null then 'finNULL' else 'finSet' end f,
case when m.id is null then 'msgGONE' else 'msgLIVE' end m2,count(*)
from gc_execution_queue q left join gc_messages m on m.id=q.messageId
where q.startedAt is null and q.createdAt>? group by 1,2,3""",(W,)): print(r)
print("== E: pair only msgGONE/LIVE ==")
for r in q("""select q.targetAgentName,case when m.id is null then 'msgGONE' else 'msgLIVE' end m2,q.status,count(*)
from gc_execution_queue q left join gc_messages m on m.id=q.messageId
where q.createdAt>? and q.targetAgentName in ('build-engineer','powervr-monkey') group by 1,2,3""",(W,)): print(r)
