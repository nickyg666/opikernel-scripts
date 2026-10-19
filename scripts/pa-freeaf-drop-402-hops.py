
import sqlite3, json, os, time, shutil
DB = "/var/lib/omniroute/storage.sqlite"
BK = "/home/host/opikernel/agentic-pool/combo-backups"
os.makedirs(BK, exist_ok=True)
c = sqlite3.connect(DB)
cur = c.cursor()
name, data = cur.execute("select name, data from combos where name='omni/freeAF'").fetchone()
d = json.loads(data)
before = [m["model"] for m in d["models"]]
drop_prefix = "opencode-zen/"
keep = [m for m in d["models"] if not m.get("model","").startswith(drop_prefix)]
dropped = [m["model"] for m in d["models"] if m.get("model","").startswith(drop_prefix)]
stamp = time.strftime("%Y%m%d-%H%M%S")
bkfile = os.path.join(BK, "omni-freeAF-drop-zen-%s.json" % stamp)
open(bkfile, "w").write(data)
print("BACKUP %s %d B md5_pending" % (bkfile, os.path.getsize(bkfile)))
print("DROPPED(%d) %s" % (len(dropped), dropped))
if dropped:
    d["models"] = keep
    d["repairNote"] = (d.get("repairNote","") + " || 2026-09-20 15:2x (PA): removed 5 opencode-zen/* hops from this combo - "
        "keyed lane, no OPENCODE_ZEN key usable upstream, every turn on those hops returned HTTP 402 payment_required "
        "(~3.4k calls each, 0 ok in call_logs). Reorder alone was insufficient: the selector still reached them.")
    cur.execute("update combos set data=? where name='omni/freeAF'", (json.dumps(d),))
    c.commit()
chk = cur.execute("select typeof(data), length(data) from combos where name='omni/freeAF'").fetchone()
print("AFTER typeof=%s len=%s n=%d models[0]=%s" % (chk[0], chk[1], len(keep), keep[0]["model"]))
