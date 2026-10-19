#!/usr/bin/env python3
"""PA dispatch probe: why do claimable build-engineer/powervr-monkey rows stay queued?
Read-only. No board/serial/power.
"""
import sqlite3, hashlib, os, re, json

DB = "/home/host/.hermes-web-ui/hermes-web-ui.db"
BUNDLE = "/usr/local/lib/node_modules/hermes-web-ui/dist/server/index.js"
ROOM = "mti5ax1clq0zlx"
TARGETS = ("build-engineer", "powervr-monkey", "PA")

print("== bundle ==")
st = os.stat(BUNDLE)
md5 = hashlib.md5(open(BUNDLE, 'rb').read()).hexdigest()
print(BUNDLE, st.st_size, md5)

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
cur = con.cursor()
print("\n== gc_execution_queue columns ==")
cols = [r[1] for r in cur.execute("pragma table_info(gc_execution_queue)")]
print(cols)

print("\n== last 2h, room, status x startedAtNULL by agent ==")
q = """select targetAgentName, status, count(*), sum(startedAt is null)
       from gc_execution_queue
       where roomId=? and createdAt > (strftime('%s','now')-7200)*1000
       group by 1,2 order by 1,2"""
for r in cur.execute(q, (ROOM,)):
    print(r)

print("\n== all-time running rows (any room) ==")
for r in cur.execute("select targetAgentName, count(*) from gc_execution_queue where status='running' group by 1 order by 2 desc"):
    print(r)

print("\n== newest 8 rows for the stalled pair ==")
q2 = """select id, targetAgentName, status, startedAt, createdAt, substr(coalesce(lastError,''),1,40)
        from gc_execution_queue where targetAgentName in ('build-engineer','powervr-monkey')
        order by createdAt desc limit 8"""
for r in cur.execute(q2):
    print(r)

print("\n== distinct lastError on queued rows ==")
for r in cur.execute("select targetAgentName, count(*), substr(coalesce(lastError,'<null>'),1,60) from gc_execution_queue where status='queued' group by 1,3 order by 2 desc limit 12"):
    print(r)
con.close()

print("\n== bundle: gate tokens before the per-row claim ==")
data = open(BUNDLE, 'rb').read()
for tok in (b'startExecutionQueueItem', b'_drainMentionQueue', b'not connected', b'isPaused', b'_pausedRooms'):
    offs = [m.start() for m in re.finditer(re.escape(tok), data)]
    print(tok.decode(), "count", len(offs), "first", offs[:6])
