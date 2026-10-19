#!/usr/bin/env python3
"""PA RCA: who zeroed agentic-pool/BACKLOG.md at 12:11:47? Hunt every write-ish row
across ALL rooms in the 12:05-12:14 window (content, tool_calls, tool_name)."""
import json
import sqlite3

DB = "/home/host/.hermes-web-ui/hermes-web-ui.db"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
lo = con.execute("select strftime('%s','2026-09-20 12:04:00')*1000").fetchone()[0]
hi = con.execute("select strftime('%s','2026-09-20 12:14:00')*1000").fetchone()[0]
rows = con.execute(
    "select datetime(timestamp/1000,'unixepoch','localtime') t, roomId, senderName, "
    "coalesce(tool_name,''), content, coalesce(tool_calls,'') "
    "from gc_messages where timestamp between ? and ? order by timestamp", (lo, hi)
).fetchall()
con.close()
print(f"rows in window: {len(rows)}")
hits = 0
for t, room, who, tool, content, calls in rows:
    blob = (content or "") + " " + (calls or "")
    if "agentic-pool/BACKLOG.md" in blob or "write_file" in blob or ">"  in blob[:0]:
        hits += 1
        flat = blob.replace("\n", " ")
        print(f"\n[{t}] {who} room={room} tool={tool}\n  {flat[:400]}")
print(f"\nwrite-ish hits: {hits}")
