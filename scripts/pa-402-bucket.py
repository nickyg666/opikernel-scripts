
import sqlite3, time
c = sqlite3.connect("file:/home/host/.hermes-web-ui/hermes-web-ui.db?mode=ro", uri=True)
cur = c.cursor()
room = "mti5ax1clq0zlx"
print("NOW", time.strftime("%H:%M:%S"))
pat = "(content like '%This model requires an opencode API key%' or content like '%Billing or credits exhausted%' or content like 'HTTP 401: No active credentials%' or content like '%rate limit%')"
rows = cur.execute("select timestamp, senderName, substr(content,1,150) from gc_messages where roomId=? and senderType='agent' and "+pat+" and julianday(timestamp/1000.0,'unixepoch') > julianday('now','-40 minutes') order by timestamp", (room,)).fetchall()
print("FAILBODIES_40min", len(rows))
from collections import Counter
buck = Counter()
for ts, s, t in rows:
    buck[time.strftime("%H:%M", time.localtime(ts/1000.0))] += 1
print("BY_MIN", dict(sorted(buck.items())))
print("LAST5")
for ts, s, t in rows[-5:]:
    print("  ", time.strftime("%H:%M:%S", time.localtime(ts/1000.0)), s, "|", t.replace("\n"," ")[:110])
# what models are named in the newest failures
import re
models = Counter()
for ts, s, t in rows[-10:]:
    for m in re.findall(r"([a-z0-9_./-]+/[a-z0-9_.-]+(?::free)?): (?:model|rate limit|provider)", t):
        models[m] += 1
print("MODELS_IN_NEWEST_FAILS", models.most_common(8))
# is the API key storm gone?
for pat2, label in [("%This model requires an opencode API key%","opencode_402"),
                    ("%No active credentials for provider: omni%","omni_401"),
                    ("%rate limit%","rate_limit_429"),
                    ("%Stream ended before producing%","stream_502")]:
    n = cur.execute("select count(*) from gc_messages where roomId=? and senderType='agent' and content like ? and julianday(timestamp/1000.0,'unixepoch') > julianday('now','-40 minutes')", (room, pat2)).fetchone()[0]
    print("  %-16s %s" % (label, n))
