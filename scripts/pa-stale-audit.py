#!/usr/bin/env python3
"""PA bounded action: audit the orchestrator stale-list against live room DB + kanban + backlog."""
import os, sqlite3, time, subprocess, hashlib, json

ROOM = "mti5ax1clq0zlx"
now = time.time()
NOWMS = int(now * 1000)
out = []

# --- room DB: last post per sender (live rows) ---
db = os.path.expanduser("~/.hermes-web-ui/hermes-web-ui.db")
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
cur = con.cursor()
rows = cur.execute(
    "SELECT senderName, MAX(CAST(timestamp AS INTEGER)) FROM gc_messages "
    "WHERE roomId=? AND COALESCE(tool_name,'')<>'workspace_diff' GROUP BY senderName ORDER BY 2 DESC",
    (ROOM,),
).fetchall()
out.append("ROOM last-post (min ago) [timestamp col, ms]:")
for name, ts in rows[:14]:
    ts = int(ts or 0)
    t = ts / 1e9 if ts > 1e14 else ts / 1e3
    out.append(f"  {name:22s} {(now - t)/60:7.1f}min  raw={ts}")

# role breakdown for PA this hour (bridge-mapping anomaly)
r2 = cur.execute(
    "SELECT role, COUNT(*) FROM gc_messages WHERE roomId=? AND CAST(timestamp AS INTEGER) > ? GROUP BY role",
    (ROOM, NOWMS - 3600 * 1000),
).fetchall()
out.append(f"PA-lane check: role counts last 60min = {r2}")

# room agents live/removed
try:
    r3 = cur.execute("SELECT name, removedAt FROM gc_room_agents WHERE roomId=?", (ROOM,)).fetchall()
    live = [n for n, rem in r3 if not rem]
    dead = [n for n, rem in r3 if rem]
    out.append(f"  agents live={len(live)} {sorted(set(live))}")
    out.append(f"  agents removed={len(dead)} {sorted(set(dead))}")
except Exception as e:
    out.append(f"  gc_room_agents err: {e}")
con.close()

# --- kanban ---
try:
    kb = sqlite3.connect("file:" + os.path.expanduser("~/.hermes/kanban.db") + "?mode=ro", uri=True)
    k = kb.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status").fetchall()
    out.append(f"KANBAN {dict(k)}")
    noexp = kb.execute(
        "SELECT COUNT(*) FROM tasks WHERE status='in_progress' AND (claim_expires IS NULL OR claim_expires='')"
    ).fetchone()[0]
    tot = kb.execute("SELECT COUNT(*) FROM tasks WHERE status='in_progress'").fetchone()[0]
    out.append(f"  in_progress={tot} with_NULL_claim_expires={noexp}")
    kb.close()
except Exception as e:
    out.append(f"KANBAN err: {e}")

# --- backlog + guard ---
bp = "/home/host/opikernel/agentic-pool/BACKLOG.md"
b = open(bp, "rb").read()
out.append(f"BACKLOG {len(b)} B md5 {hashlib.md5(b).hexdigest()} open={b.count(b'status: open')}")
lg = "/home/host/opikernel/pvrgl-work/backlog-lastgood"
out.append(f"  guard log exists={os.path.exists(lg)}")

# --- obsidian ---
vault = "/home/host/opikernel-obsidian/Memory"
n = sum(1 for f in os.listdir(vault) if os.path.isfile(os.path.join(vault, f)))
recent = sorted(
    ((os.path.getmtime(os.path.join(vault, f)), f) for f in os.listdir(vault) if f.endswith(".md")),
    reverse=True,
)[:3]
out.append(f"OBSIDIAN {n} files, newest: " + "; ".join(f"{f} {time.strftime('%H:%M', time.localtime(m))}" for m, f in recent))

print("\n".join(out))
