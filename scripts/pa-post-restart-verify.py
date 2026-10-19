#!/usr/bin/env python3
"""PA post-restart verify: probe the CLIENT port (the one hermes config uses).

Config: base_url http://192.168.0.168:20128/v1/ model omni/freeAF
Earlier probes hit 127.0.0.1:8080 instead -> different listener, so its timeouts
were NOT representative of what agent turns experience.
"""
import json
import time
import urllib.request
import urllib.error

URL = "http://192.168.0.168:20128/v1/chat/completions"


def probe(model, timeout=150):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "reply with the single word: ok"}],
        "max_tokens": 8,
        "stream": False,
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            j = json.loads(raw)
            return r.status, round(time.time() - t0, 2), str(j.get("model", "?"))
    except urllib.error.HTTPError as e:
        return e.code, round(time.time() - t0, 2), e.read().decode("utf-8", "replace")[:100]
    except Exception as e:  # noqa: BLE001
        return "ERR", round(time.time() - t0, 2), f"{type(e).__name__}: {e}"[:100]


for _ in range(2):
    print("omni/freeAF ->", probe("omni/freeAF"), flush=True)
    print("freecode    ->", probe("freecode"), flush=True)
