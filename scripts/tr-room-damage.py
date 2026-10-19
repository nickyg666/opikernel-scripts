#!/usr/bin/env python3
"""TR: quantify self-inflicted room damage vs real work, + starved-lane census."""
import sqlite3, time, os

ROOM = "mti5ax1clq0zlx"
GC = "/home/host/.hermes-web-ui/hermes-web-ui.db"
now_ms = int(time.time() * 1000)
win = 40 * 60 * 1000

con = sqlite3.connect(f"file:{GC}?mode=ro", uri=True)
c = con.cursor()

# schema sniff
cols = [r[1] for r in c.execute("PRAGMA table_info(gc_messages)")]
tcol = "createdAt" if "createdAt" in cols else cols[0]
scol = "senderName" if "senderName" in cols else ("sender" if "sender" in cols else cols[1])
bcol = "body" if "body" in cols else ("content" if "content" in cols else cols[-1])

rows = c.execute(
    f"SELECT {scol}, {bcol}, length({bcol}) FROM gc_messages "
    f"WHERE roomId=? AND {tcol} > ?", (ROOM, now_ms - win)).fetchall()

n = len(rows)
per = {}
prov = drift = 0
for s, b, L in rows:
    b = b or ""
    per[s] = per.get(s, 0) + 1
    if "Billing or credits exhausted" in b or "rate limit" in b or "Invalid API key" in b:
        prov += 1
    if "repeat-within-message" in b or "drift-guard" in b:
        drift += 1

print(f"ROOM {ROOM} last 40min: msgs={n} | provider-error={prov} | drift-guard={drift} | real={n-prov-drift}")
print("by sender: " + " · ".join(f"{k}={v}" for k, v in sorted(per.items(), key=lambda x: -x[1])))

# queue census across rooms
q = c.execute(
    "SELECT targetAgentName, COUNT(*), SUM(startedAt IS NULL OR startedAt='') "
    "FROM gc_execution_queue WHERE status='queued' "
    "GROUP BY targetAgentName ORDER BY 2 DESC").fetchall()
print("QUEUED(all rooms) agent=total/null-start: " + " · ".join(f"{a}={t}/{s}" for a, t, s in q))
maxrun = c.execute(
    "SELECT targetAgentName, MAX(?-startedAt) FROM gc_execution_queue WHERE status='running' AND startedAt IS NOT NULL GROUP BY targetAgentName",
    (now_ms,)).fetchall()
print("RUNNING age(s): " + " · ".join(f"{a}={int(g/1000)}" for a, g in maxrun))
con.close()

log = "/home/host/opikernel/pvrgl-work/sercap_room_live.log"
st = os.stat(log)
print(f"GATE: capture={st.st_size}B frozen={time.strftime('%m-%d_%H:%M:%S', time.localtime(st.st_mtime))}")
