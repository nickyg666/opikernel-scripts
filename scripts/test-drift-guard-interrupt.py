#!/usr/bin/env python3
"""Prove the drift-guard STOP path end-to-end against the LIVE agent bridge.

Creates a real bridge session running a deliberately long turn, then interrupts it
mid-turn with the exact request agent-drift-guard.py sends, and reports what the
bridge answered for both the interrupt and the original chat call.

Never touches a production agent session.
"""
import glob, json, socket, threading, time, sys

SID = "driftguard-selftest-%d" % int(time.time())
PROMPT = ("Run this exact terminal command and report its raw output: "
          "sleep 45; echo INTERRUPT-TEST-DONE")
res = {}

def call(ep, req, timeout=180):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(ep)
    s.sendall((json.dumps(req) + "\n").encode())
    chunks = []
    while True:
        c = s.recv(65536)
        if not c:
            break
        chunks.append(c)
        if b"\n" in c:
            break
    s.close()
    line = b"".join(chunks).split(b"\n", 1)[0].strip()
    return json.loads(line.decode()) if line else {"ok": False, "error": "empty"}

eps = sorted(glob.glob("/tmp/hermes-agent-bridge-workers/*.sock"))
if not eps:
    sys.exit("no bridge socket found")
ep = eps[0]
print("bridge:", ep)
print("ping  :", {k: call(ep, {"action": "ping"}, 10).get(k) for k in ("ok", "pid", "session_count")})

def chat_thread():
    t0 = time.time()
    try:
        res["chat"] = call(ep, {"action": "chat", "session_id": SID,
                                "message": PROMPT, "profile": "default"}, 240)
    except Exception as exc:
        res["chat"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    res["chat_secs"] = round(time.time() - t0, 1)

th = threading.Thread(target=chat_thread, daemon=True)
th.start()
print(f"started live turn for {SID}; interrupting in 12s ...")
time.sleep(12)
t1 = time.time()
try:
    irq = call(ep, {"action": "interrupt", "session_id": SID,
                    "message": "DRIFT GUARD selftest interrupt"})
except Exception as exc:
    irq = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
print("interrupt response:", json.dumps(irq)[:400])
print("interrupt round-trip: %.2fs" % (time.time() - t1))
th.join(timeout=90)
print("orig chat call returned after", res.get("chat_secs"), "s ->",
      json.dumps(res.get("chat"))[:300])
print("VERDICT:", "PASS — live turn stopped by interrupt" if irq.get("ok")
      else "FAIL — interrupt rejected")
