#!/usr/bin/env python3
"""PA RCA pass 4 - backlog-worker1's own tool_calls around the 12:11:47 truncation."""
import sqlite3
import time

DB = "/home/host/.hermes-web-ui/hermes-web-ui.db"
mk = lambda s: int(time.mktime(time.strptime(s, "%Y-%m-%d %H:%M:%S"))) * 1000
lo, hi = mk("2026-09-20 12:05:00"), mk("2026-09-20 12:20:00")
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
for r in con.execute(
    "select datetime(timestamp/1000,'unixepoch','localtime'), senderName, coalesce(tool_name,'-'), "
    "content, coalesce(tool_calls,'') from gc_messages where timestamp between ? and ? "
    "and (senderName like 'backlog%' or senderName like 'Backlog%') order by timestamp", (lo, hi)
):
    t, who, tool, content, calls = r
    print(f"\n=== [{t}] {who} tool={tool}")
    if tool != "-":
        print("  res:", content[:300].replace("\n", " "))
    if calls:
        print("  CALLS:", calls[:800].replace("\n", " "))
    if tool == "-" and content.strip():
        print("  msg:", content[:300].replace("\n", " "))
con.close()
