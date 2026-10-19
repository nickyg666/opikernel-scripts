#!/usr/bin/env python3
"""PA probe: does a reaped twin make a queued row permanently unclaimable?
Tests the 18:38 hypothesis: enqueue dedupes on (messageId,targetAgentId) and hands
back the EXISTING row (even one already 'failed'), while the drain claims only
status='queued' -> a re-pushed mention is silently discarded.
Read-only DB access. Room-scoped.
"""
import sqlite3, sys

DB = "/home/host/.hermes-web-ui/hermes-web-ui.db"
ROOM = "mti5ax1clq0zlx"
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
c.row_factory = sqlite3.Row

# 1. live queued rows in this room, oldest first, with the agent name
q = c.execute("""
    select id, messageId, targetAgentId, targetAgentName, status, createdAt, startedAt, lastError
    from gc_execution_queue
    where roomId=? and status='queued'
    order by createdAt asc
""", (ROOM,)).fetchall()
print(f"queued_in_room={len(q)}")
import collections
byname = collections.Counter((r["targetAgentName"] or r["targetAgentId"]) for r in q)
print("queued_by_agent:", dict(byname))

# 2. for each agent with queued rows, does any (messageId,targetAgentId) pair have >1 row?
print("\n--- DUPLICATE-PAIR TEST (the dedupe claim) ---")
pairs = collections.Counter((r["messageId"], r["targetAgentId"]) for r in q)
dups = {k: v for k, v in pairs.items() if v > 1}
print(f"pairs={len(pairs)} pairs_with_more_than_1_row={len(dups)}")

# 3. global duplicate-pair test (any status) - proves dedupe exists or not
g = c.execute("""
    select messageId, targetAgentId, count(*) n, group_concat(status) sts
    from gc_execution_queue
    where roomId=?
    group by messageId, targetAgentId
    having n > 1
    order by n desc limit 8
""", (ROOM,)).fetchall()
print(f"\n--- ROOM-WIDE pairs with >1 row (top 8 of all) ---")
for r in g:
    print(f"  n={r['n']} statuses={r['sts']}")

# 4. head rows: oldest queued per the two stuck agents + every row ever for that pair
print("\n--- HEAD ROW 4x: every row ever created for its (messageId,targetAgentId) ---")
heads = sorted(q, key=lambda r: r["createdAt"])[:40]
seen = set()
for r in heads:
    nm = r["targetAgentName"] or r["targetAgentId"]
    key = (nm, r["messageId"], r["targetAgentId"])
    if nm in seen:
        continue
    seen.add(nm)
    rows = c.execute("""
        select id,status,createdAt,startedAt,lastError from gc_execution_queue
        where messageId=? and targetAgentId=?
        order by createdAt asc
    """, (r["messageId"], r["targetAgentId"])).fetchall()
    sts = collections.Counter(x["status"] for x in rows)
    print(f"  {nm}: rows_for_pair={len(rows)} statuses={dict(sts)} head_createdAt={r['createdAt']}")
    for x in rows:
        print(f"     {x['status']:<9} created={x['createdAt']} started={x['startedAt']} err={x['lastError']}")

# 5. does the message still exist in gc_messages? (deliverable vs reaped)
print("\n--- MESSAGE EXISTENCE for queued rows ---")
live = 0
gone = 0
for r in q:
    e = c.execute("select 1 from gc_messages where id=?", (r["messageId"],)).fetchone()
    if e:
        live += 1
    else:
        gone += 1
print(f"queued rows with message PRESENT={live} DELETED={gone}")

# 6. epoch-ms sanity: newest queued row age
import time
now_ms = int(time.time() * 1000)
print(f"\nnow_ms={now_ms}")
for r in q[:3]:
    print(f"  newest-ish {r['targetAgentName']}: age_min={(now_ms - r['createdAt'])/60000:.1f}")
oldest = min(r["createdAt"] for r in q) if q else 0
if q:
    print(f"  oldest queued age_min={(now_ms - oldest)/60000:.1f}")
