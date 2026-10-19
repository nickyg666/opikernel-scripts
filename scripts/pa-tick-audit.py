#!/usr/bin/env python3
"""PA bounded tick: queue/board parity + single-claim + phantom-path scan."""
import hashlib, os, re, sqlite3, subprocess, sys

BL = "/home/host/opikernel/agentic-pool/BACKLOG.md"
DB = os.path.expanduser("~/.hermes/kanban.db")

raw = open(BL, "rb").read()
md5 = hashlib.md5(raw).hexdigest()
txt = raw.decode("utf-8", "replace")

# split into item blocks on '### BL-'
items = {}
cur = None
for line in txt.splitlines():
    m = re.match(r"^###\s+(BL-\d+)", line)
    if m:
        cur = m.group(1)
        items[cur] = {"status": None, "by": None}
        continue
    if cur:
        s = re.match(r"^\s*status:\s*(\S+)", line)
        if s:
            items[cur]["status"] = s.group(1)
        c = re.match(r"^\s*claimed-by:\s*(\S+)", line)
        if c:
            items[cur]["by"] = c.group(1)

print(f"BACKLOG.md md5={md5} bytes={len(raw)} ids={len(items)} range={min(items, key=lambda k:int(k[3:]))}..{max(items, key=lambda k:int(k[3:]))}")
from collections import Counter
print("file status:", dict(Counter(v["status"] for v in items.values())))

# owners holding >1 non-open item (single-claim rule)
hold = Counter(v["by"] for v in items.values() if v["by"] and v["status"] not in ("done",))
multi = {k: c for k, c in hold.items() if c > 1}
print("file multi-claim owners:", multi or "none")

# board
if os.path.exists(DB):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    q = con.execute("select count(*) from tasks").fetchone()[0]
    blrows = con.execute("select count(*) from tasks where title like 'BL-%'").fetchone()[0]
    inprog = con.execute(
        "select assignee, count(*) from tasks where status='in_progress' group by assignee").fetchall()
    dupin = {a: c for a, c in inprog if c > 1}
    print(f"board tasks={q} BLrows={blrows} in_progress_by={dict(inprog) or 'none'} board multi-in-progress: {dupin or 'none'}")
    ids = set(r[0] for r in con.execute(
        "select substr(title,1,5) from tasks where title like 'BL-%'"))
    print("board-only ids:", sorted(ids - set(items)) or "none", "| file-only ids:", sorted(set(items) - ids) or "none")
    con.close()
else:
    print("board: MISSING", DB)

# phantom-path scan across agentic-pool docs
needles = ["c77b48ec", "eb1bd6e7", "bsp-graft-73-dwarf", "modules-rebuild-pinctrl-g", "BL-23", "BL-29"]
hits = {}
for fn in os.listdir("/home/host/opikernel/agentic-pool"):
    if not fn.endswith(".md"):
        continue
    p = os.path.join("/home/host/opikernel/agentic-pool", fn)
    try:
        t = open(p, encoding="utf-8", errors="replace").read()
    except OSError:
        continue
    for n in needles:
        if n in t:
            hits.setdefault(n, []).append(fn)
print("phantom needles in queue/docs:", {k: v for k, v in hits.items()} or "none")

print("staging dir exists:", os.path.isdir("/home/host/opikernel/staging"))
print("real lock:", subprocess.run(["stat", "-c", "%s bytes mtime %y",
      "/tmp/kdir-7.3.build.lock"], capture_output=True, text=True).stdout.strip() or "absent")
