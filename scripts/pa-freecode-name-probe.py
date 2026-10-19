#!/usr/bin/env python3
"""PA bounded probe 22:2x: is the *real* row name 'freecode' live, or did I
probe a nonexistent combo name 'omni/freecode' and call the pool dead?"""
import json, time, urllib.request

URL = "http://192.168.0.168:20128/v1/chat/completions"
BODY = {"model": None, "messages": [{"role": "user", "content": "reply with OK"}],
        "max_tokens": 4, "stream": False}

for model in ("freecode", "omni/freecode", "omni/freeAF"):
    b = dict(BODY, model=model)
    req = urllib.request.Request(URL, data=json.dumps(b).encode(),
                                headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read().decode("utf-8", "replace")
            served = r.headers.get("x-omniroute-model") or r.headers.get("x-served-by") or "?"
            txt = json.loads(raw).get("choices", [{}])[0].get("message", {}).get("content", "")[:40]
            print(f"{model:16s} http={r.status} t={time.time()-t0:.2f}s served-by={served} txt={txt!r}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:110].replace("\n", " ")
        print(f"{model:16s} http={e.code} t={time.time()-t0:.2f}s {body}")
    except Exception as e:
        print(f"{model:16s} ERR {type(e).__name__}: {str(e)[:80]}")
