#!/usr/bin/env python3
"""PA RCA pass 2 - correct timezone window (store is epoch ms UTC).

Also answers: what did the 12:15 kanban sync do while the queue was 0 bytes?
"""
import sqlite3

DB = "/home/host/.hermes-web-ui/hermes-web-ui.db"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
lo, hi = con.execute(
    "select strftime('%s','now','-70 minutes')*1000, strftime('%s','now','-40 minutes')*1000"
).fetchone()
print(f"window {lo} .. {hi} (epoch ms)")
rows = con.execute(
    "select datetime(timestamp/1000,'unixepoch','localtime'), roomId, senderName, "
    "coalesce(tool_name,''), substr(replace(content,char(10),' '),1,220), coalesce(tool_calls,'') "
    "from gc_messages where timestamp between ? and ? and tool_name is not null "
    "order by timestamp", (lo, hi)
).fetchall()
print(f"tool rows in window: {len(rows)}")
for t, room, who, tool, content, calls in rows:
    if "BACKLOG" in content or "BACKLOG" in calls or tool in ("write_file", "patch"):
        print(f"\n[{t}] {who} tool={tool} room={room}\n  {content[:260]}\n  calls={calls[:200]}")
con.close()
