#!/usr/bin/env python3
"""PA probe #3: one message, all its rows -> per-target split. Plus insert/claim sites in the bundle."""
import sqlite3, re

DB = "/home/host/.hermes-web-ui/hermes-web-ui.db"
BUNDLE = "/usr/local/lib/node_modules/hermes-web-ui/dist/server/index.js"
ROOM = "mti5ax1clq0zlx"
MID = "gcbash-1789943632604-1ebc03"

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
cur = con.cursor()

print("== message text (first 600 chars) ==")
row = cur.execute("select senderName, substr(content,1,600) from gc_messages where id=?", (MID,)).fetchone()
print(row)

print("\n== every queue row for that messageId ==")
for r in cur.execute("""select targetAgentName, targetAgentId, status, startedAt, sequence,
                               length(coalesce(textSummary,'')), coalesce(lastError,'<null>')
                        from gc_execution_queue where messageId=? order by createdAt""", (MID,)):
    print(r)

print("\n== room membership ids ==")
for r in cur.execute("select id, agentId, name, removedAt from gc_room_agents where roomId=?", (ROOM,)):
    print(r)

data = open(BUNDLE, 'rb').read()
print("\n== insert/claim sites ==")
for tok in (b'gc_execution_queue', b'insertExecutionQueueItem', b'enqueueMention', b'queueId'):
    offs = [m.start() for m in re.finditer(re.escape(tok), data)]
    print(tok.decode(), len(offs), offs[:10])

print("\n== storage insert window 10957300..10958600 ==")
print(data[10957300:10958600].decode('utf-8', 'replace'))
con.close()
