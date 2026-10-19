#!/usr/bin/env python3
"""PA probe #2: read the drain's target-build + drop gates at byte level; join stuck rows to gc_messages."""
import sqlite3, re, json, datetime

DB = "/home/host/.hermes-web-ui/hermes-web-ui.db"
BUNDLE = "/usr/local/lib/node_modules/hermes-web-ui/dist/server/index.js"
ROOM = "mti5ax1clq0zlx"

data = open(BUNDLE, 'rb').read()
print("== drain window 10713960..10715120 ==")
print(data[10713960:10715120].decode('utf-8', 'replace'))

print("\n== who builds a.target / targets (search tokens) ==")
for tok in (b'targets', b'agentMention', b'mentionIds', b'targetAgentName', b'undelivered'):
    offs = [m.start() for m in re.finditer(re.escape(tok), data)]
    print(tok.decode(), len(offs), offs[:12])

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
cur = con.cursor()

print("\n== epoch check ==")
print("now ms", cur.execute("select cast(strftime('%s','now') as integer)*1000").fetchone()[0],
      "newest stuck row 1789943632612 =",
      datetime.datetime.fromtimestamp(1789943632).strftime('%Y-%m-%d %H:%M:%S'))

print("\n== last 2h: queue row vs gc_messages existence, by agent ==")
q = """select targetAgentName, (m.id is not null) as msgexists, q.status, count(*), sum(q.startedAt is null)
       from gc_execution_queue q left join gc_messages m on m.id = q.messageId
       where q.roomId=? and q.createdAt > (strftime('%s','now')-7200)*1000
       group by 1,2,3 order by 1,2,3"""
for r in cur.execute(q, (ROOM,)):
    print(r)

print("\n== of the messages that queued build-engineer/powervr-monkey, did ANY sibling row start? ==")
q2 = """select q.messageId, q.targetAgentName, q.status,
               (select count(*) from gc_execution_queue x where x.messageId=q.messageId and x.status in ('running','completed')) as sib_started,
               (m.id is not null) as msg_exists
        from gc_execution_queue q left join gc_messages m on m.id=q.messageId
        where q.roomId=? and q.targetAgentName in ('build-engineer','powervr-monkey')
          and q.createdAt > (strftime('%s','now')-3600)*1000
        order by q.createdAt desc limit 12"""
for r in cur.execute(q2, (ROOM,)):
    print(r)
con.close()
