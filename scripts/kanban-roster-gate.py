#!/usr/bin/env python3
"""Room-aware kanban assignee gate.

WHY: the kanban DB (~/.hermes/kanban.db) is SHARED by every Hermes group-chat room
(Neorunner mti3yr2g3yjpyr, KernelDev-GPU mti5ax1clq0zlx, ...), and rows carry no
tenant/project_id. A gate that checks an assignee against ONE room's roster therefore
flags the other room's perfectly dispatchable rows as "undeliverable" and incites
releases that orphan live work.

RULE: an assignee is undeliverable only when it is live in NO room
(gc_room_agents.removedAt IS NULL/0). Rows absent from *this* room are reported as
FOREIGN, not orphaned -- never release them.

Usage: kanban-roster-gate.py [--room mti5ax1clq0zlx] [--json]
Exit: 0 = no true orphans, 1 = true orphan(s) found, 2 = cannot read a DB.
"""
import argparse, json, os, sqlite3, sys

KANBAN = os.path.expanduser(os.environ.get("HERMES_KANBAN_DB", "~/.hermes/kanban.db"))
WEBUI = os.path.expanduser(os.environ.get("HERMES_WEBUI_DB", "~/.hermes-web-ui/hermes-web-ui.db"))
OPEN_STATES = ("done", "archived", "cancelled")


def rosters(path):
    """{roomId: {agent_name_lower: agentId}} for agents still in each room."""
    con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    out = {}
    q = ("select roomId,name,agentId from gc_room_agents "
         "where coalesce(removedAt,0)=0")
    for room, name, aid in con.execute(q):
        out.setdefault(room, {})[(name or "").strip().lower()] = aid
    names = {}
    for rid, nm in con.execute("select id,name from gc_rooms"):
        names[rid] = nm
    return out, names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", default=os.environ.get("HERMES_ROOM_ID", "mti5ax1clq0zlx"),
                    help="room to report FOREIGN vs OK for (default KernelDev-GPU)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    for p in (KANBAN, WEBUI):
        if not os.path.exists(p):
            print("UNREADABLE %s" % p, file=sys.stderr)
            return 2
    try:
        room, rnames = rosters(WEBUI)
    except sqlite3.Error as e:
        print("WEBUI READ FAIL %s" % e, file=sys.stderr)
        return 2

    live_any = set()
    for m in room.values():
        live_any |= set(m)

    con = sqlite3.connect("file:%s?mode=ro" % KANBAN, uri=True)
    q = ("select id,status,assignee,created_by,idempotency_key,substr(title,1,70) "
         "from tasks where coalesce(assignee,'')<>'' and status not in (%s) "
         "order by status,id" % ",".join("?" * len(OPEN_STATES)))
    rows = list(con.execute(q, OPEN_STATES))

    orphan, foreign, ok, in_progress_bad = [], [], [], []
    for tid, status, assignee, cb, ikey, title in rows:
        name = assignee.strip().lower()
        row = {"id": tid, "status": status, "assignee": assignee,
               "created_by": cb, "key": ikey, "title": title}
        if name in live_any:
            where = sorted(room_ids for room_ids, m in room.items() if name in m)
            row["rooms"] = where
            (ok if a.room in where else foreign).append(row)
            if status == "in_progress" and a.room not in where:
                in_progress_bad.append(row)
        else:
            orphan.append(row)

    if a.json:
        print(json.dumps({"room": a.room, "orphans": orphan, "foreign": foreign,
                          "ok": ok, "rosters": {k: sorted(v) for k, v in room.items()}},
                         indent=2))
    else:
        print("room=%s (%s)  roster=%d  live-anywhere names=%d  open rows w/ assignee=%d"
              % (a.room, rnames.get(a.room, "?"), len(room.get(a.room, {})),
                 len(live_any), len(rows)))
        print("\n-- TRUE ORPHANS (assignee live in NO room -> genuinely releaseable): %d"
              % len(orphan))
        for r in orphan:
            print("   %s %-12s %-22s key=%s  %s"
                  % (r["id"], r["status"], r["assignee"], r["key"], r["title"]))
        print("\n-- FOREIGN (valid elsewhere -- DO NOT release): %d" % len(foreign))
        for r in foreign:
            print("   %s %-12s %-22s rooms=%s  %s"
                  % (r["id"], r["status"], r["assignee"], ",".join(r["rooms"]), r["title"]))
        print("\n-- OK in room: %d" % len(ok))
    if in_progress_bad:
        print("\nWARN %d in_progress row(s) assigned to agents not in room %s "
              "(deliverable elsewhere; re-assign in-room or leave to owning room)"
              % (len(in_progress_bad), a.room))
    return 1 if orphan else 0


if __name__ == "__main__":
    sys.exit(main())
