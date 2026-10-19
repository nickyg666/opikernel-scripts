#!/usr/bin/env python3
"""PA: probe each target of a combo and reorder live-hop-first.

Classifies per-hop: 200=live, 402=dead-entitlement (guaranteed fail),
000/timeout=hung. Writes live -> hung -> dead, keeping all entries.
Uses CAST(readfile(...) AS TEXT) to avoid the sqlite3 BLOB trap.
Never prints credentials. --apply to write, otherwise dry-run.
"""
import json, sqlite3, subprocess, sys, time, datetime, shutil, os

DB = "/var/lib/omniroute/storage.sqlite"
URL = "http://192.168.0.168:20128/v1/chat/completions"
COMBO = sys.argv[1] if len(sys.argv) > 1 else "omni/freeAF"
APPLY = "--apply" in sys.argv
HOP_TIMEOUT = "15"

con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
row = con.execute("SELECT id, typeof(data), data FROM combos WHERE name=?", (COMBO,)).fetchone()
assert row, "combo not found"
cid, kind, data = row
assert kind == "text", "data is %s — repair with UPDATE ... CAST(data AS TEXT)" % kind
cfg = json.loads(data)
models = cfg["models"]


def probe(model):
    body = json.dumps({"model": model, "max_tokens": 8,
                       "messages": [{"role": "user", "content": "ping"}]})
    t0 = time.time()
    p = subprocess.run(["curl", "-s", "-o", "/tmp/pa_probe_hop.json", "-w", "%{http_code}",
                        "-m", HOP_TIMEOUT, "-X", "POST", URL,
                        "-H", "Content-Type: application/json", "-d", body],
                       capture_output=True, text=True)
    code = p.stdout.strip()
    dt = time.time() - t0
    err = ""
    if code != "200":
        try:
            j = json.load(open("/tmp/pa_probe_hop.json"))
            err = str(j.get("error", j))[:70]
        except Exception:
            err = ""
    return code, round(dt, 2), err, code == "200"


results = []
for m in models:
    code, dt, err, ok = probe(m.get("model"))
    results.append((m, code, dt, err, ok))
    print("%-45s %-4s %6.2fs %s" % (m.get("model"), code, dt, err))

live = [r[0] for r in results if r[4]]
hung = [r[0] for r in results if r[1] in ("000", "504", "408") or r[2] >= 24]
dead = [r[0] for r in results if not r[4] and r[1] not in ("000", "504", "408") and r[2] < 24]
new = live + hung + dead
print("live=%d hung=%d dead=%d (total %d)" % (len(live), len(hung), len(dead), len(new)))
if not APPLY:
    print("dry-run; --apply to write")
    sys.exit(0)

cfg["models"] = new
bakdir = "/home/host/opikernel/agentic-pool/combo-backups"
os.makedirs(bakdir, exist_ok=True)
stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
bak = os.path.join(bakdir, "%s-%s.json" % (COMBO.replace("/", "-"), stamp))
shutil.copyfile("/tmp/pa_freeaf_models_pre.json", bak) if os.path.exists("/tmp/pa_freeaf_models_pre.json") else None
open(bak, "w").write(json.dumps({"models": models}, indent=1))
tmp = "/tmp/pa_combo_new.json"
cfg_txt = json.dumps(cfg)
open(tmp, "w").write(cfg_txt)
con.close()
w = sqlite3.connect(DB)
# NOTE: python's sqlite3 has no readfile() (CLI-only extension). Bind the TEXT directly.
w.execute("UPDATE combos SET data=?, updated_at=? WHERE id=?",
          (cfg_txt, datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"), cid))
w.commit()
chk = w.execute("SELECT typeof(data), json_extract(data,'$.models[0].model') FROM combos WHERE id=?", (cid,)).fetchone()
print("post-write typeof=%s first=%s backup=%s" % (chk[0], chk[1], bak))
w.close()
for i in range(3):
    code, dt, err, ok = probe(COMBO)
    print("combo probe %d: %s %.2fs %s" % (i + 1, code, dt, err))
