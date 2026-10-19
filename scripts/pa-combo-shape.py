
import sqlite3, json
c = sqlite3.connect("file:/var/lib/omniroute/storage.sqlite?mode=ro", uri=True)
cur = c.cursor()
name, data = cur.execute("select name, data from combos where name='omni/freeAF'").fetchone()
d = json.loads(data)
print("TOPKEYS", list(d.keys()))
print("STRATEGY", d.get("strategy"), "| fallback-ish keys:", {k:v for k,v in d.items() if k!="models" and not isinstance(v,(list,dict))})
for i, m in enumerate(d["models"]):
    print(i, json.dumps(m)[:220])
