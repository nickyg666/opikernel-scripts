#!/usr/bin/env python3
"""PA RCA pass 3 - pin the 12:11:47 truncation: exact 12:08-12:13 local window, ALL rooms."""
import sqlite3
import time

DB = "/home/host/.hermes-web-ui/hermes-web-ui.db"
mk = lambda s: int(time.mktime(time.strptime(s, "%Y-%m-%d %H:%M:%S"))) * 1000
lo, hi = mk("2026-09-20 12:07:00"), mk("2026-09-20 12:14:00")
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
rows = con.execute(
    "select datetime(timestamp/1000,'unixepoch','localtime'), roomId, senderName, "
    "coalesce(tool_name,''), substr(replace(content,char(10),' '),1,300), coalesce(tool_calls,'') "
    "from gc_messages where timestamp between ? and ? order by timestamp", (lo, hi)
).fetchall()
print(f"ALL rows 12:07-12:14 local: {len(rows)}")
for t, room, who, tool, content, calls in rows:
    blob = content + " " + calls
    flag = ""
    if "BACKLOG" in blob:
        flag = "<<< BACKLOG"
    if tool == "write_file" and '"bytes_written": 0' in blob:
        flag += " <<< ZERO-BYTE WRITE"
    if flag or tool in ("write_file", "patch"):
        print(f"[{t}] {who:16s} room={room[:12]} tool={tool:9s} {flag}\n    {content[:240]}")
con.close()
