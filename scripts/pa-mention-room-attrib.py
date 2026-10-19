#!/bin/bash
# PA: attribute MENTION REJECTED lines to the room block they sit in
L=/home/host/opikernel/logs/group-orchestrator.log
python3 - "$L" <<'PY'
import re,sys,collections
room=None; cur=None
rej=collections.Counter(); fb=collections.Counter()
stalelines=[]
for ln in open(sys.argv[1],errors='ignore'):
    m=re.match(r'\[(mti\w+)\] stale=\[(.*?)\]',ln)
    if m: room=m.group(1); cur=m.group(2).split(); continue
    if 'MENTION REJECTED' in ln:
        a=re.search(r"unknown agent '([^']*)'",ln)
        if a: rej[(room,a.group(1))]+=1
    if 'falling back to local yolo spawn' in ln: fb[room]+=1
print("REJECTIONS grouped by (room the tick was serving, rejected agent):")
for (r,a),c in rej.most_common(12): print(f"  {r}  {a:20s} {c}")
print("FALLBACK SPAWNS by room:",dict(fb))
PY
echo "--- who is in each roster ---"
python3 - <<'PY'
import sqlite3
c=sqlite3.connect('file:/home/host/.hermes-web-ui/hermes-web-ui.db?mode=ro',uri=True); c.execute('.timeout 8000')
for rid, in c.execute("select distinct roomId from gc_room_agents"):
    n=[r[0] for r in c.execute("select name from gc_room_agents where roomId=? and removedAt=0 order by name",(rid,))]
    print(f"  {rid} ({len(n)}): {' '.join(n)}")
PY
