#!/usr/bin/env python3
"""PA: reorder omni/freeAF so the probe-verified WORKING hops lead.

Evidence base (15:00:39 direct-target probe, scripts/pa-combo-reprobe.sh):
  [3] huggingface/deepseek-ai/DeepSeek-V3       200 6.67s
  [4] nvidia/nvidia/nemotron-3-super-120b-a12b  200 3.35s  (tool_calls=True verified)
  [0-2] opencode/*-free                         000 timeout 25s  (upstream client-gated)
  [5-9] opencode-zen/*                          402 billing_error (dead entitlement)
  [10-11] openrouter/*:free                     000 timeout 25s  (daily cap / hang)
Writes a dated backup beside the DB row, then reorders models: working-first, dead-last.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

DB = "/var/lib/omniroute/storage.sqlite"
BAK_DIR = "/home/host/opikernel/agentic-pool/combo-backups"
COMBO = "omni/freeAF"

WORKING_LEAD = [
    "nvidia/nvidia/nemotron-3-super-120b-a12b",
    "huggingface/deepseek-ai/DeepSeek-V3",
]
# dead-but-keep: fast-fail 402 hops (cheap), then the 25s hang group absolutely last
FAST_FAIL = [
    "opencode-zen/glm-5.3-flash",
    "opencode-zen/deepseek-v4-flash",
    "opencode-zen/qwen3.8-flash",
    "opencode-zen/deepseek-v4-pro",
    "opencode-zen/minimax-m3",
]
HANG_LAST = [
    "opencode/mimo-v2.5-free",
    "opencode/deepseek-v4-flash-free",
    "opencode/nemotron-3-ultra-free",
    "openrouter/dots-studio/dots-3-note-preview:free",
    "openrouter/nex-agi/nex-n2.5-pro:free",
]


def main(apply_write: bool):
    os.makedirs(BAK_DIR, exist_ok=True)
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    row = con.execute("select data from combos where name=?", (COMBO,)).fetchone()
    con.close()
    if not row:
        print("FATAL: combo not found")
        return 1
    d = json.loads(row[0])
    models = d["models"]
    by_id = {m["model"]: m for m in models}
    order = WORKING_LEAD + FAST_FAIL + HANG_LAST
    missing = [m for m in order if m not in by_id]
    orphan = [m for m in by_id if m not in order]
    if missing or orphan:
        print(f"FATAL: order mismatch missing={missing} orphan={orphan} — refusing to write")
        return 2
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = f"{BAK_DIR}/{COMBO.replace('/', '-')}-{stamp}.json"
    with open(bak, "w") as f:
        f.write(row[0])
    old_first = models[0]["model"]
    d["models"] = [by_id[m] for m in order]
    d["updatedAt"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    print(f"backup: {bak} ({os.path.getsize(bak)} B)")
    print(f"old order[0]: {old_first}")
    print("new order:", " -> ".join(order))
    pool = (d.get("config") or {}).get("candidatePool")
    print("candidatePool:", pool)
    if not apply_write:
        print("(dry run — no write)")
        return 0
    tmp = "/tmp/pa-freeaf-new.json"
    with open(tmp, "w") as f:
        json.dump(d, f)
    r = subprocess.run(
        [
            "sudo",
            "-n",
            "sqlite3",
            DB,
            f"UPDATE combos SET data=readfile('{tmp}'), updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE name='{COMBO}';",
        ],
        capture_output=True,
        text=True,
    )
    os.unlink(tmp)
    if r.returncode != 0:
        print("WRITE FAILED:", r.stderr.strip()[:300])
        return 3
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    chk = con.execute("select data from combos where name=?", (COMBO,)).fetchone()[0]
    con.close()
    c = json.loads(chk)
    print("verify after write: new order[0] =", c["models"][0]["model"], "| count", len(c["models"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(apply_write="--apply" in sys.argv))
