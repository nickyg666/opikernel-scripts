#!/usr/bin/env python3
"""Name-vs-agentId twin hazard probe for the dead-lane predicate.

scripts/lane-wedge-check.py groups gc_execution_queue by targetAgentName, but the
web-ui drain guard is keyed room\\0agentId. If one NAME owns two live agentIds
(twins), a wedge on one agentId's key is masked whenever the other twin
completes, because max(finishedAt) is taken per NAME.

Read-only. Prints, per duplicate name: each agentId's completions + last
completion, and which twin the name-keyed max() lands on.

DB path: $WEDGE_DB if set, else the same default as lane-wedge-check.py.
"""
import os
import sqlite3
import sys

DEFAULT_DB = os.path.expanduser("~/.hermes-web-ui/hermes-web-ui.db")
DB = os.environ.get("WEDGE_DB", DEFAULT_DB)
ROOM = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WEDGE_ROOM", "")

if not os.path.exists(DB):
    print(f"FAIL db missing: {DB}")
    raise SystemExit(2)

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row

cols = [r[1] for r in con.execute("PRAGMA table_info(gc_room_agents)")]
idcol = "agentId" if "agentId" in cols else ("id" if "id" in cols else cols[0])
namecol = "name" if "name" in cols else ("agentName" if "agentName" in cols else cols[1])
print(f"db={DB}\ngc_room_agents idcol={idcol} namecol={namecol}")

dups = list(con.execute(
    f"""SELECT {namecol} AS nm, COUNT(*) AS n,
               group_concat({idcol}) AS ids
          FROM gc_room_agents
         WHERE removedAt=0 AND {namecol} IS NOT NULL
      GROUP BY {namecol} HAVING COUNT(*) > 1 ORDER BY n DESC"""))
print(f"live names owning >1 agentId: {len(dups)}")
for d in dups:
    print(f"  {d['nm']}: n={d['n']} ids={d['ids']}")

q = """SELECT {idcol} AS aid,
              sum(status='completed') AS ok,
              sum(status='failed') AS bad,
              sum(status='queued') AS queued,
              max(CASE WHEN status='completed' THEN finishedAt END) AS last_ok
         FROM gc_execution_queue
        WHERE roomId=? AND targetAgentName=? AND {idcol} IS NOT NULL
     GROUP BY {idcol}"""

# resolve the agentId column on the queue table too (name may differ)
qcols = [r[1] for r in con.execute("PRAGMA table_info(gc_execution_queue)")]
qid = "agentId" if "agentId" in qcols else ("targetAgentId" if "targetAgentId" in qcols else None)
if qid is None:
    print("FAIL no agentId column on gc_execution_queue; cannot prove per-twin split")
    raise SystemExit(2)

for d in dups:
    nm = d["nm"]
    print(f"\n-- name {nm} (queue grouped per agentId, room={ROOM or 'ALL'})")
    sql = q.format(idcol=qid)
    rows = list(con.execute(sql, (ROOM, nm))) if ROOM else list(
        con.execute(sql.replace("roomId=? AND ", ""), (nm,)))
    for r in rows:
        print(f"   agentId={r['aid']} completed={r['ok']} failed={r['bad']} "
              f"queued={r['queued']} last_completed={r['last_ok']}")
    if rows:
        winner = max(rows, key=lambda r: (r["last_ok"] or 0))
        print(f"   name-keyed max(finishedAt) lands on agentId={winner['aid']} "
              f"-> a wedge on any other twin is MASKED")
