#!/usr/bin/env python3
"""PA bounded action: queue parity + kanban policing + 402 tail + drift-guard + vault."""
import hashlib, os, sqlite3, subprocess, time, json, glob

ROOT = "/home/host/opikernel"
def md5(p):
    try:
        return hashlib.md5(open(p, "rb").read()).hexdigest()
    except Exception as e:
        return "ERR:%s" % e

b = os.path.join(ROOT, "agentic-pool/BACKLOG.md")
lg = os.path.join(ROOT, "agentic-pool/BACKLOG.md.lastgood")
print("QUEUE  BACKLOG.md %d B md5 %s" % (os.path.getsize(b), md5(b)))
print("QUEUE  .lastgood  %d B md5 %s" % (os.path.getsize(lg), md5(lg)))
print("QUEUE  parity: %s" % ("IDENTICAL" if md5(b) == md5(lg) else "DRIFTED"))

# --- kanban ---
kb = "/home/host/.hermes/kanban.db"
try:
    c = sqlite3.connect("file:%s?mode=ro" % kb, uri=True)
    cur = c.cursor()
    cols = [r[1] for r in cur.execute("pragma table_info(tasks)")]
    scol = "status" if "status" in cols else cols[0]
    tcol = "title" if "title" in cols else None
    acol = "assignee" if "assignee" in cols else ("claimed_by" if "claimed_by" in cols else None)
    rows = list(cur.execute("select %s, %s, %s from tasks" % (scol, tcol, acol)))
    from collections import Counter
    print("KANBAN total=%d %s" % (len(rows), dict(Counter(r[0] for r in rows))))
    keys = Counter((r[1], r[2]) for r in rows if r[0] in ("in_progress", "claimed"))
    dups = {k: v for k, v in keys.items() if v > 1}
    print("KANBAN dup title|assignee in in_progress/claimed: %s" % (dups or "none"))
except Exception as e:
    print("KANBAN ERR %s" % e)

# --- resolve live group chat DB from running node process ---
gc = None
try:
    out = subprocess.run(["sudo", "ls", "-l", "/proc/self/fd"], capture_output=True, text=True).stdout
except Exception:
    out = ""
cand = "/home/host/.hermes-web-ui/hermes-web-ui.db"
if os.path.exists(cand):
    gc = cand
print("GC_DB  %s (exists=%s size=%d)" % (gc, os.path.exists(cand), os.path.getsize(cand) if os.path.exists(cand) else -1))

if gc:
    try:
        c = sqlite3.connect("file:%s?mode=ro" % gc, uri=True)
        cur = c.cursor()
        cur.execute("select id, name from gc_rooms")
        rooms = cur.fetchall()
        room = None
        for rid, name in rooms:
            if "mti5" in (rid or "") or (name and "ernel" in name):
                room = rid
        print("GC     rooms=%s -> using %s" % (len(rooms), room))
        if room:
            q = ("select count(*) from gc_messages where roomId=? and senderType='agent' "
                 "and (content like '%This model requires an opencode API key%' "
                 "or content like '%Billing or credits exhausted%' "
                 "or content like 'HTTP 401: No active credentials%') "
                 "and julianday(timestamp/1000.0,'unixepoch') > julianday('now','-15 minutes')")
            print("402    15min count=%s" % cur.execute(q, (room,)).fetchone()[0])
            q2 = ("select max(timestamp) from gc_messages where roomId=? ")
            mx = cur.execute(q2, (room,)).fetchone()[0]
            print("GC     newest ts=%s" % mx)
            q3 = ("select senderName, count(*) from gc_messages where roomId=? "
                  "and julianday(timestamp/1000.0,'unixepoch') > julianday('now','-15 minutes') "
                  "group by senderName order by 2 desc")
            print("GC     15min by sender: %s" % cur.execute(q3, (room,)).fetchall())
    except Exception as e:
        print("GC ERR %s" % e)

# --- drift guard log ---
for p in ["/home/host/opikernel/agentic-pool/drift-guard.log",
          "/home/host/opikernel/logs/drift-guard.log",
          "/home/host/.hermes/logs/drift-guard.log"]:
    if os.path.exists(p):
        sz = os.path.getsize(p)
        mt = time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(p)))
        tail = subprocess.run(["tail", "-n", "3", p], capture_output=True, text=True).stdout.strip().replace("\n", " | ")
        print("DRIFT  %s %d B @%s :: %s" % (p, sz, mt, tail[:220]))
        break
else:
    print("DRIFT  no log at the 3 known paths")

# --- obsidian vault ---
v = "/home/host/opikernel-obsidian/Memory"
if os.path.isdir(v):
    files = glob.glob(os.path.join(v, "**", "*.md"), recursive=True)
    newest = max(files, key=os.path.getmtime) if files else None
    print("VAULT  %d notes, newest %s @%s" % (
        len(files), os.path.basename(newest) if newest else "-",
        time.strftime("%m-%d_%H:%M:%S", time.localtime(os.path.getmtime(newest))) if newest else "-"))

# --- freeAF combo post-fix probe ---
try:
    t0 = time.time()
    r = subprocess.run(["curl", "-s", "-m", "30", "-o", "/tmp/pa_probe.json", "-w", "%{http_code}",
                        "http://192.168.0.168:20128/v1/chat/completions",
                        "-H", "Content-Type: application/json",
                        "-d", json.dumps({"model": "omni/freeAF",
                                          "messages": [{"role": "user", "content": "reply OK"}],
                                          "max_tokens": 8})],
                       capture_output=True, text=True)
    dt = time.time() - t0
    body = open("/tmp/pa_probe.json").read()[:120] if os.path.exists("/tmp/pa_probe.json") else ""
    print("ROUTER omni/freeAF HTTP %s in %.2fs :: %s" % (r.stdout.strip(), dt, body.replace("\n", " ")))
except Exception as e:
    print("ROUTER ERR %s" % e)
