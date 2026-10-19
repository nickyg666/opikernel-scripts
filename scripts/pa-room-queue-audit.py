#!/usr/bin/env python3
"""PA audit: room queue state + which lanes hold undrained 'queued' rows."""
import sqlite3, time, sys
from collections import Counter

DB = "/home/host/.hermes-web-ui/hermes-web-ui.db"
RID = sys.argv[1] if len(sys.argv) > 1 else "mti5ax1clq0zlx"
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
c.row_factory = sqlite3.Row
now = time.time() * 1000

print("queue cols:", [r[1] for r in c.execute("PRAGMA table_info(gc_execution_queue)")])
rows = c.execute(
    "SELECT targetAgentId,status,createdAt,lastError FROM gc_execution_queue "
    "WHERE roomId=? ORDER BY createdAt DESC LIMIT 60", (RID,)).fetchall()
print(f"room={RID} rows_last60={len(rows)}", dict(Counter(r["status"] for r in rows)))
for r in rows[:16]:
    print(" ", r["status"], r["targetAgentId"], f"{int((now-r['createdAt'])/1000)}s",
          (r["lastError"] or "")[:44])
if rows:
    allrows = c.execute(
        "SELECT status,createdAt FROM gc_execution_queue WHERE roomId=?", (RID,)).fetchall()
    print("all-time:", dict(Counter(r["status"] for r in allrows)))

# live lanes + last message + any live running/queued row  (mirrors nudge predicate)
print("--- lanes ---")
for a in c.execute("SELECT agentId,name FROM gc_room_agents WHERE roomId=? "
                   "AND (removedAt IS NULL OR removedAt=0)", (RID,)).fetchall():
    m = c.execute("SELECT timestamp FROM gc_messages WHERE roomId=? AND senderName=? "
                  "ORDER BY timestamp DESC LIMIT 1", (RID, a["name"])).fetchone()
    age = (now - m["timestamp"]) / 60000.0 if m and m["timestamp"] else -1
    live = c.execute("SELECT count(*) n FROM gc_execution_queue WHERE roomId=? AND "
                     "targetAgentId=? AND status IN ('running','queued') AND createdAt>?",
                     (RID, a["agentId"], now - 10 * 60000)).fetchone()["n"]
    print(f"  {a['name']:<20} last_msg={age:7.1f}m  live_running/queued_10m={live}")
