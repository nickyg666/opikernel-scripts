#!/usr/bin/env python3
"""PA: rank a combo's targets by REAL served success from OmniRoute's own call log,
then rewrite the combo live-first (by ok-rate), keeping every entry (0-ok hops last).

Why: a single probe is noisy (and parallel probing saturates the router), while
call_logs holds the last N minutes of authoritative status per requested model.

usage: pa-combo-rank-by-log.py [combo] [minutes] [--apply]
"""
import json, sqlite3, subprocess, sys, time, datetime, os

DB = "/var/lib/omniroute/storage.sqlite"
URL = "http://192.168.0.168:20128/v1/chat/completions"
args = [a for a in sys.argv[1:] if not a.startswith("-")]
COMBO = args[0] if args else "omni/freeAF"
MINS = int(args[1]) if len(args) > 1 else 30
APPLY = "--apply" in sys.argv

con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
cid, kind, data = con.execute("SELECT id, typeof(data), data FROM combos WHERE name=?", (COMBO,)).fetchone()
assert kind == "text", "data is %s" % kind
cfg = json.loads(data)
models = cfg["models"]

stats = {}
for mdl, n, ok, c402, c429 in con.execute(
        "SELECT coalesce(requested_model,model), count(*), sum(status=200), sum(status=402), sum(status=429) "
        "FROM call_logs WHERE julianday(timestamp) > julianday('now', ?) GROUP BY 1", ("-%d minutes" % MINS,)):
    stats[mdl] = (n, ok, c402, c429)


def rate(m):
    n, ok, c402, c429 = stats.get(m, (0, 0, 0, 0))
    return (ok / n) if n else -1.0, n, ok, c402, c429


rows = [(m.get("model"),) + rate(m.get("model")) for m in models]
rows.sort(key=lambda r: (-r[1] if r[1] > 0 else 1, -r[2]))
for r in rows:
    print("%-50s calls=%-5d ok=%-5d 402=%-5d 429=%-5d okrate=%s" %
          (r[0], r[2], r[3], r[4], r[5], ("%.0f%%" % (r[1] * 100)) if r[1] > 0 else "n/a"))

if not APPLY:
    print("dry-run; --apply to reorder")
    sys.exit(0)

order = {r[0]: i for i, r in enumerate(rows)}
cfg["models"] = sorted(models, key=lambda m: order.get(m.get("model"), 999))
bakdir = "/home/host/opikernel/agentic-pool/combo-backups"
os.makedirs(bakdir, exist_ok=True)
stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
bak = os.path.join(bakdir, "%s-ranked-%s.json" % (COMBO.replace("/", "-"), stamp))
open(bak, "w").write(json.dumps({"models": models}, indent=1))
con.close()
w = sqlite3.connect(DB)
w.execute("UPDATE combos SET data=?, updated_at=? WHERE id=?",
          (json.dumps(cfg), datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"), cid))
w.commit()
chk = w.execute("SELECT typeof(data), json_extract(data,'$.models[0].model'), json_array_length(json_extract(data,'$.models')) FROM combos WHERE id=?", (cid,)).fetchone()
print("post-write typeof=%s first=%s count=%d backup=%s" % (chk[0], chk[1], chk[2], bak))
w.close()

for i in range(3):
    t0 = time.time()
    p = subprocess.run(["curl", "-s", "-o", "/tmp/pa_combo_probe.json", "-w", "%{http_code}",
                        "-m", "40", "-X", "POST", URL, "-H", "Content-Type: application/json",
                        "-d", json.dumps({"model": COMBO, "max_tokens": 8,
                                          "messages": [{"role": "user", "content": "ping"}]})],
                       capture_output=True, text=True)
    served = ""
    try:
        served = json.load(open("/tmp/pa_combo_probe.json")).get("model", "")
    except Exception:
        pass
    print("combo probe %d: http=%s %.2fs served=%s" % (i + 1, p.stdout.strip(), time.time() - t0, served))
