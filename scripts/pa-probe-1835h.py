#!/usr/bin/env python3
"""PA probe #8: backlog age per agent = wedge evidence. Queued rows are only claimed or reaped,
so a row that stays 'queued' for many minutes proves the drain never reached it.
"""
import sqlite3, datetime

DB = "/home/host/.hermes-web-ui/hermes-web-ui.db"
ROOM = "mti5ax1clq0zlx"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
cur = con.cursor()
now = cur.execute("select cast(strftime('%s','now') as integer)*1000").fetchone()[0]

print("== per agent: oldest/newest still-queued row, count, backlog age (min) ==")
q = """select targetAgentName, count(*), min(createdAt), max(createdAt)
       from gc_execution_queue where roomId=? and status='queued'
       group by 1 order by 3 asc"""
for name, c, mn, mx in cur.execute(q, (ROOM,)):
    print(f"{name:16s} n={c:3d} oldest={datetime.datetime.fromtimestamp(mn/1000):%H:%M:%S} "
          f"age={(now-mn)/60000:7.1f}m newest={datetime.datetime.fromtimestamp(mx/1000):%H:%M:%S}")

print("\n== head-of-backlog row for the stalled pair: its message + sibling statuses ==")
for name in ('build-engineer', 'powervr-monkey'):
    r = cur.execute("""select id, messageId, targetAgentId, createdAt from gc_execution_queue
                       where roomId=? and status='queued' and targetAgentName=?
                       order by sequence asc limit 1""", (ROOM, name)).fetchone()
    if not r:
        print(name, "no queued row")
        continue
    rid, mid, taid, ts = r
    print(f"\n{name}: row={rid} msg={mid} at={datetime.datetime.fromtimestamp(ts/1000):%H:%M:%S}")
    for s in cur.execute("""select targetAgentName, status, startedAt, finishedAt, substr(coalesce(lastError,''),1,50)
                            from gc_execution_queue where messageId=? order by sequence""", (mid,)):
        print("   sib:", s)
    m = cur.execute("select senderName, substr(content,1,90) from gc_messages where id=?", (mid,)).fetchone()
    print("   msg:", m)

print("\n== how the AGENTS THAT RUN look: their oldest queued backlog age ==")
for name in ('PA', 'TelegramRunner', 'kconfig-auditor', 'debugger'):
    r = cur.execute("""select count(*), min(createdAt) from gc_execution_queue
                       where roomId=? and status='queued' and targetAgentName=?""", (ROOM, name)).fetchone()
    if r and r[1]:
        print(f"{name:16s} n={r[0]:3d} oldest_age={(now-r[1])/60000:7.1f}m")
    else:
        print(f"{name:16s} n=0  (no backlog at all)")
con.close()
