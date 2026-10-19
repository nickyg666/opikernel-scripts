
import json, subprocess, time, sqlite3, os
def probe(tag):
    t0 = time.time()
    p = subprocess.run(["curl","-s","-m","45","-o","/tmp/pa_p.json","-w","%{http_code}",
        "http://192.168.0.168:20128/v1/chat/completions","-H","Content-Type: application/json",
        "-d", json.dumps({"model":"omni/freeAF","stream":False,"max_tokens":8,
                          "messages":[{"role":"user","content":"reply with the single word OK"}]})],
        capture_output=True, text=True)
    dt = time.time()-t0
    body = open("/tmp/pa_p.json").read() if os.path.exists("/tmp/pa_p.json") else ""
    try:
        j = json.loads(body)
        served = j.get("model") or (j.get("choices") or [{}])[0].get("model")
        msg = (j.get("choices") or [{}])[0].get("message",{}).get("content","")
        err = j.get("error")
        desc = "served=%s msg=%r err=%s" % (served, (msg or "")[:40], (str(err)[:90] if err else None))
    except Exception as e:
        desc = "body[:120]=%r parse_err=%s" % (body[:120], e)
    print("PROBE %-6s HTTP %s in %.2fs :: %s" % (tag, p.stdout.strip(), dt, desc))
for i in range(2):
    probe("post%d"%(i+1)); time.sleep(1)
# raw shape sanity: first hop entry
c = sqlite3.connect("file:/var/lib/omniroute/storage.sqlite?mode=ro", uri=True)
d = json.loads(c.execute("select data from combos where name='omni/freeAF'").fetchone()[0])
print("HOP0", json.dumps(d["models"][0]))
