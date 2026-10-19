
import sqlite3, time, glob, os
g = sqlite3.connect("file:/home/host/.hermes-web-ui/hermes-web-ui.db?mode=ro", uri=True)
cur = g.cursor()
pat = "(content like '%This model requires an opencode API key%' or content like '%Billing or credits exhausted%' or content like 'HTTP 401: No active credentials%')"
ts0 = 1789932439000  # 15:27:19 EDT
rows = cur.execute("select timestamp, senderName, substr(content,1,90) from gc_messages where roomId='mti5ax1clq0zlx' and senderType='agent' and "+pat+" and timestamp > ? order by timestamp", (ts0,)).fetchall()
print("FAILS_SINCE_1527:19", len(rows))
for t,s,c in rows[-6:]:
    print("  ", time.strftime("%H:%M:%S", time.localtime(t/1000.0)), s, "|", c.replace("\n"," ")[:80])
last = cur.execute("select max(timestamp) from gc_messages where roomId='mti5ax1clq0zlx'").fetchone()[0]
print("NEWEST_ROOM_MSG", time.strftime("%H:%M:%S", time.localtime(last/1000.0)))
print("NOW", time.strftime("%H:%M:%S"))
cands = glob.glob("/home/host/opikernel/**/drift*guard*", recursive=True)[:8]
print("DRIFT_FILES", [(os.path.basename(p), os.path.getsize(p), time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(p)))) for p in cands])
