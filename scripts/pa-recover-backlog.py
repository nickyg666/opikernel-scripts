#!/usr/bin/env python3
"""PA: recover agentic-pool/BACKLOG.md (truncated to 0 bytes at 12:11:47).

Evidence trail: last known good = TR patch 12:05 -> md5 eae0c4f3bec86ec97685c09af6d8d3c7 (26,576 B).
Base snapshot on disk: BACKLOG.md.bak @09:58:40 (25,509 B, 24 items).
Damage delta = 26,576 - 25,509 = 1,067 B == TR's +11-line BL-24 flip.
So: restore .bak, replay TR's own diff from the room DB, verify md5 == eae0c4f3.
"""
import json
import pathlib
import shutil
import sqlite3
import subprocess

POOL = pathlib.Path("/home/host/opikernel/agentic-pool")
TARGET = POOL / "BACKLOG.md"
BAK = POOL / "BACKLOG.md.bak"
DB = "/home/host/.hermes-web-ui/hermes-web-ui.db"
WANT_MD5 = "eae0c4f3bec86ec97685c09af6d8d3c7"

# --- 0. preserve the 0-byte corpse as evidence ---
if TARGET.stat().st_size == 0 and not (POOL / "BACKLOG.md.zeroed-20260920-121147").exists():
    shutil.copy2(TARGET, POOL / "BACKLOG.md.zeroed-20260920-121147")
    print("[0] zero-byte corpse preserved as BACKLOG.md.zeroed-20260920-121147")

# --- 1. harvest TR's own patch from the live room DB ---
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
rows = con.execute(
    "select datetime(timestamp/1000,'unixepoch','localtime'), senderName, content "
    "from gc_messages where tool_name='patch' and content like '%BACKLOG.md%' "
    "and content like '%BL-24%' order by timestamp desc limit 5"
).fetchall()
con.close()
diff = None
for ts, who, content in rows:
    try:
        obj = json.loads(content)
    except Exception:
        continue
    d = obj.get("diff") or ""
    if "BL-24" in d and "@@ -344" in d:
        diff = d
        print(f"[1] harvested diff from {who} @{ts} ({len(d)} B)")
        break
if diff is None:
    print("[1] FAIL: no usable BL-24 diff in room DB")
    raise SystemExit(1)

pf = pathlib.Path("/tmp/pa-bl24.patch")
# DB stores the diff header as '--- a//abs/path'; rewrite both headers to -p1 form
lines = diff.splitlines(True)
fixed = []
for ln in lines:
    if ln.startswith("--- a/"):
        ln = "--- a/agentic-pool/BACKLOG.md\n"
    elif ln.startswith("+++ b/"):
        ln = "+++ b/agentic-pool/BACKLOG.md\n"
    fixed.append(ln)
pf.write_text("".join(fixed))
print("[1] patch written (/tmp/pa-bl24.patch)")

# --- 2. restore base + apply ---
shutil.copy2(BAK, TARGET)
r = subprocess.run(["patch", "-p1", "-d", "/home/host/opikernel", "-i", str(pf)],
                   capture_output=True, text=True)
print(f"[2] patch rc={r.returncode} {r.stdout.strip()} {r.stderr.strip()}")
if r.returncode != 0:
    shutil.copy2(BAK, TARGET)
    print("[2] FAIL: reverted to .bak base, manual rebuild needed")
    raise SystemExit(1)

# --- 3. verify against the recorded md5 ---
raw = TARGET.read_bytes()
md5 = subprocess.run(["md5sum", str(TARGET)], capture_output=True, text=True).stdout.split()[0]
items = raw.decode().count("\n### BL-")
print(f"[3] bytes={len(raw)} (want 26576) md5={md5} (want {WANT_MD5}) items={items} (want 24)")
print("[3] EXACT MATCH" if md5 == WANT_MD5 else "[3] MISMATCH - do not claim recovery")
