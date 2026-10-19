#!/usr/bin/env python3
"""PA bounded probe 19:20 — is the per-(room,agent) mention-queue wedge still live,
did the 19:19 digest's claimed 13->14 come from a real claim, and has anyone
fired the clear-context lever? Read-only. No board/serial/power touched."""
import os, re, sqlite3, subprocess, glob, time, json

ROOM = "mti5ax1clq0zlx"
TARGETS = ("build-engineer", "powervr-monkey")
REPO = "/home/host/opikernel"

# --- 1. resolve the LIVE web-ui db from the running node server, not a guess ---
db = None
for pid in [p for p in os.listdir("/proc") if p.isdigit()]:
    try:
        cmd = open(f"/proc/{pid}/cmdline", "rb").read().decode("utf8", "replace")
    except Exception:
        continue
    if "hermes-web-ui" not in cmd or "node" not in cmd:
        continue
    try:
        for fd in os.listdir(f"/proc/{pid}/fd"):
            try:
                t = os.readlink(f"/proc/{pid}/fd/{fd}")
            except Exception:
                continue
            if t.endswith("hermes-web-ui.db") and os.path.exists(t):
                db = t
                print(f"DB pid={pid} path={t}")
                break
    except PermissionError:
        continue
    if db:
        break
if not db:
    db = "/home/host/.hermes-web-ui/hermes-web-ui.db"
    print(f"DB fallback={db}")

con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
con.row_factory = sqlite3.Row

tabs = [r[0] for r in con.execute(
    "select name from sqlite_master where type='table' and (name like '%queue%' or name like '%mention%')")]
print("QUEUE TABLES:", tabs)

for t in tabs:
    cols = [c[1] for c in con.execute(f"pragma table_info({t})")]
    if "agentId" not in cols:
        continue
    print(f"\n== {t} cols={cols}")
    q = f"""select agentId,
        sum(case when startedAt is null then 1 else 0 end) as never_started,
        sum(case when startedAt is not null then 1 else 0 end) as started,
        count(*) as n,
        max(createdAt) as newest_created,
        max(startedAt) as newest_started
      from {t} where roomId=? group by agentId order by never_started desc"""
    try:
        for r in con.execute(q, (ROOM,)):
            print(dict(r))
    except Exception as e:
        print("  groupby failed:", e)
        continue
    for a in TARGETS:
        try:
            rs = list(con.execute(
                f"select id,status,createdAt,startedAt,lastError from {t} "
                f"where roomId=? and agentId=? order by createdAt desc limit 4", (ROOM, a)))
        except Exception as e:
            print(f"  {a}: select failed {e}")
            continue
        print(f"  -- {a} newest4:")
        for r in rs:
            print("    ", dict(r))
        if "lastError" in cols:
            for r in con.execute(
                f"select lastError,count(*) c from {t} where roomId=? and agentId=? "
                f"and lastError is not null group by lastError", (ROOM, a)):
                print(f"    err {dict(r)}")

con.close()

# --- 2. BACKLOG.md state census (claimed 13 -> 14?) ---
bl = os.path.join(REPO, "agentic-pool/BACKLOG.md")
txt = open(bl, encoding="utf8", errors="replace").read()
states = re.findall(r"^\s*(?:-\s*)?\**state\**\s*[:=]\s*(\w+)", txt, re.M)
from collections import Counter
print("\nBACKLOG.md states:", dict(Counter(s.lower() for s in states)), "lines=", txt.count("\n"))
try:
    st = subprocess.run(["python3", os.path.join(REPO, "scripts/backlog-guard.py"), "--lint"],
                        capture_output=True, text=True, cwd=REPO, timeout=60)
    print("guard:", (st.stdout or st.stderr).strip()[:400])
except Exception as e:
    print("guard failed:", e)

# --- 3. clear-context lever: any recent hit on the endpoint / any web-ui restart? ---
try:
    out = subprocess.run(["bash", "-lc",
        "ps -eo pid,etime,cmd | grep -F 'hermes-web-ui' | grep -v grep | head -5"],
        capture_output=True, text=True, timeout=30).stdout.strip()
    print("\nWEBUI PROCS:\n" + (out or "(none)"))
except Exception as e:
    print("ps failed:", e)
print("\nNOW", time.strftime("%Y-%m-%d %H:%M:%S"))
