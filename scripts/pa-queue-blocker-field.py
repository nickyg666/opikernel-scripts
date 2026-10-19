#!/usr/bin/env python3
"""PA: derive the orchestrator digest's `blockers=` field from gc_execution_queue.

Why (RCA 2026-09-20 17:16, room mti5ax1clq0zlx): the digest printed
`stale=@build-engineer @powervr-monkey ... blockers=none` in 13/13 posts while
those two agents' mentions were being reaped undelivered (264 / 244 rows
`undelivered_reaped_by_room_guard`, status=queued, startedAt NULL). The
placeholder could not distinguish "working" from "never dispatched", so the room
kept whipping two agents whose mentions never arrived.

Rule: an agent NAMED in the digest that has zero `completed` rows and a non-zero
`failed`/`queued` count inside the window HAS a blocker, and it is a delivery
blocker, not an empty field.

Read-only. Never fails the digest: any error prints `none`.
Usage: pa-queue-blocker-field.py <roomId> <agent> [agent...]
"""
import os
import sqlite3
import sys
import time

DB = os.environ.get("DB_GC", "/home/host/.hermes-web-ui/hermes-web-ui.db")
# RCA 2026-09-20 20:05 (PA): the reap deadline is ~35 min, so a 30-min window could
# NEVER contain a reaped delivery -- every digest read "Nneverstarted" while the
# truth was status='failed' + lastError='undelivered_reaped_by_room_guard'. Window
# must exceed the deadline or the field hides the blocker it exists to report.
WINDOW_MIN = int(os.environ.get("PA_BLOCK_WINDOW_MIN", "45"))


def main():
    if len(sys.argv) < 3:
        print("none")
        return
    room, names = sys.argv[1], sys.argv[2:]
    since = int((time.time() - WINDOW_MIN * 60) * 1000)
    try:
        con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
        rows = con.execute(
            "SELECT targetAgentName, status, COUNT(*) FROM gc_execution_queue "
            "WHERE roomId=? AND createdAt>? GROUP BY 1,2",
            (room, since),
        ).fetchall()
        con.close()
    except Exception as exc:  # a broken field must never kill a digest post
        sys.stderr.write("pa-queue-blocker-field: %s\n" % exc)
        print("none")
        return

    agg = {}
    for name, status, count in rows:
        agg.setdefault(name, {})[status] = count

    out = []
    for name in names:
        d = agg.get(name) or {}
        ok = d.get("completed", 0)
        fail = d.get("failed", 0)
        queued = d.get("queued", 0)
        if ok == 0 and (fail or queued):
            out.append("%s(0ok/%dfail/%dqueued)" % (name, fail, queued))
    print(" ".join(out) if out else "none")


main()
