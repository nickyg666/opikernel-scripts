#!/usr/bin/env python3
"""PA: find LIVE tool-capable hops for the agent stack.

Scans synced available models for a set of providers and probes each candidate
against the local OmniRoute at :20128 in a thread pool. Prints only hops that
answer 200, with latency, so a combo can be led by a genuinely live hop.

usage: pa-live-hop-scan.py [max_per_provider]
"""
import json, sqlite3, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

DB = "/var/lib/omniroute/storage.sqlite"
URL = "http://192.168.0.168:20128/v1/chat/completions"
MAXP = int(sys.argv[1]) if len(sys.argv) > 1 else 6
TIMEOUT = "12"

PROVIDERS = ["huggingface", "nvidia", "ollama-cloud", "cf", "unc",
             "opencode", "opencode-zen", "opencode-go", "openrouter", "openai"]

con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
cands = []
for (prov, key) in con.execute(
        "SELECT DISTINCT substr(key,1,instr(key,':')-1), key FROM key_value "
        "WHERE namespace='syncedAvailableModels'"):
    if prov not in PROVIDERS:
        continue
    try:
        val = con.execute("SELECT value FROM key_value WHERE namespace='syncedAvailableModels' AND key=?",
                          (key,)).fetchone()[0]
        ids = json.loads(val)
    except Exception:
        continue
    if isinstance(ids, dict):
        ids = list(ids.keys())
    free = [i for i in ids if str(i).endswith(":free") or str(i).endswith("-free")]
    rest = [i for i in ids if i not in free]
    if prov == "openrouter":
        rest = [i for i in free][:MAXP]          # openrouter free only
    elif prov in ("opencode", "opencode-zen", "opencode-go"):
        rest = rest[:MAXP]
    else:
        rest = rest[:MAXP]
    for i in rest:
        if "embed" in str(i) or "audio" in str(i) or "whisper" in str(i) or "tts" in str(i):
            continue
        cands.append("%s/%s" % (prov, i))

seen, uniq = set(), []
for c in cands:
    if c not in seen:
        seen.add(c)
        uniq.append(c)
cands = uniq
print("candidates=%d" % len(cands), flush=True)


def probe(model):
    body = json.dumps({"model": model, "max_tokens": 8,
                       "messages": [{"role": "user", "content": "ping"}]})
    t0 = time.time()
    p = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                        "-m", TIMEOUT, "-X", "POST", URL,
                        "-H", "Content-Type: application/json", "-d", body],
                       capture_output=True, text=True)
    return model, p.stdout.strip(), round(time.time() - t0, 2)


live = []
with ThreadPoolExecutor(max_workers=8) as ex:
    for model, code, dt in ex.map(probe, cands):
        if code == "200":
            live.append("%s %ss" % (model, dt))
            print("LIVE %-60s %ss" % (model, dt), flush=True)
print("live=%d of %d" % (len(live), len(cands)))
