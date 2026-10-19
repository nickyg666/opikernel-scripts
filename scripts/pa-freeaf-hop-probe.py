#!/usr/bin/env python3
"""PA bounded action: probe each hop of the omni/freeAF combo row directly.

The client config points the `omni` provider at model `omni/freeAF`, strategy=priority.
Earlier "live=0" probes were artifacts (bare model ids with no provider prefix stall
without a body). Probe by DIRECT POST against the router with the combo's real hop
model ids so a fast 401/429 is distinguishable from a real 200 completion.
"""
import json
import time
import urllib.request
import urllib.error

ROUTER = "http://127.0.0.1:8080/v1/chat/completions"

HOPS = [
    ("huggingface", "huggingface/deepseek-ai/DeepSeek-V3"),
    ("nvidia", "nvidia/nvidia/nemotron-3-super-120b-a12b"),
    ("openrouter", "openrouter/dots-studio/dots-3-note-preview:free"),
    ("openrouter", "openrouter/nex-agi/nex-n2.5-pro:free"),
    ("opencode", "opencode/mimo-v2.5-free"),
    ("opencode", "opencode/deepseek-v4-flash-free"),
    ("opencode", "opencode/nemotron-3-ultra-free"),
]

BODY = {
    "model": None,
    "messages": [{"role": "user", "content": "reply with the single word: ok"}],
    "max_tokens": 8,
    "stream": False,
}


def probe(model):
    body = dict(BODY, model=model)
    req = urllib.request.Request(
        ROUTER,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=75) as r:
            raw = r.read().decode("utf-8", "replace")
            dt = time.time() - t0
            try:
                j = json.loads(raw)
                served = (j.get("model") or j.get("provider") or "?")
                content = (j.get("choices") or [{}])[0].get("message", {}).get("content", "")
                return r.status, round(dt, 2), f"served-by={served} text={content[:40]!r}"
            except Exception:
                return r.status, round(dt, 2), raw[:120]
    except urllib.error.HTTPError as e:
        dt = time.time() - t0
        return e.code, round(dt, 2), e.read().decode("utf-8", "replace")[:140]
    except Exception as e:  # noqa: BLE001
        return "ERR", round(time.time() - t0, 2), f"{type(e).__name__}: {e}"[:140]


live = 0
for provider, model in HOPS:
    status, dt, note = probe(model)
    if status == 200:
        live += 1
    print(f"{provider:<12} {model:<48} http={status} t={dt}s  {note}")

print(f"\nLIVE_HOPS={live}/{len(HOPS)}  (combo omni/freeAF, strategy=priority)")
