#!/usr/bin/env python3
"""PA: ONE live-row predicate shared by every whip path (digest + nudge).

Why (RCA 2026-09-20 23:35, room mti5ax1clq0zlx): both whip producers decide a lane is
"stale" from its last ROOM MESSAGE age. A lane that is mid-run -- or whose mention is
already sitting undrained in the queue -- still reads silent, so it is mentioned again
every cooldown. Measured with the queue ledger, room-scoped:

    powervr-monkey   1 running + 4 queued  (333s/269s/206s/15s)  -> 5 rows, 4 minted by the digest
    backlog-worker1  1 running + 3 queued  (824s/716s/652s)
    build-engineer   1 running + 2 queued  (2296s/2232s)

`scripts/kernel-room-nudge.sh` got the dedupe gate at 23:20 (QUEUE_DEDUPE_MIN=10, inline
SQL); the digest path in `scripts/group-orchestrator.sh` had NO such gate -- only
`lane_wedged()` -- so it kept minting rows for lanes that were already running. That is
the whole "queued grows while completed also grows" signature.

Rule (REVISED 2026-09-21 03:52, same room): a lane holding a RUNNING row younger than the
window is NOT idle. A lane holding only QUEUED rows is NOT idle only if that backlog is
DEMONSTRABLY draining -- its newest completed row is newer than its oldest queued row and
its oldest queued row is inside the window.

Why the old rule was self-defeating: "queued row younger than window" counted the rows the
whip itself had just minted as proof the lane was alive. Measured 03:52:
backlog-worker1 held 7 queued / 0 started / 0 completed since 02:18 (89 min dead) and this
predicate reported it as live at **96 s** -- so every mention refreshed the suppression and
the gate kept the whip off the one lane that needed it.

Contract (mirrors scripts/lane-wedge-check.py, so both paths cannot drift):
  stdout : one "name<TAB>age_s" per live lane, oldest first. Empty when none.
  rc 0   : at least one live lane (or a healthy empty result: rc is 1 then)
  rc 1   : predicate ran, no live lanes  -> safe to mention everyone
  rc 2   : predicate BROKEN (DB unreadable) -> prints NOTHING. Callers must read rc=2 as
           UNKNOWN and fall back to mentioning (the pre-fix behaviour). A broken predicate
           must never be able to silence the whip silently -- that failure mode is what
           starved four lanes on 2026-09-20 20:37.

Usage: lane-live-check.py <roomId>   [--window-min N] [--names-only]
Env:   DB_GC (default /home/host/.hermes-web-ui/hermes-web-ui.db)
"""
import os
import sqlite3
import sys
import time

DB = os.environ.get("DB_GC", "/home/host/.hermes-web-ui/hermes-web-ui.db")
DEFAULT_WINDOW_MIN = int(os.environ.get("PA_LIVE_WINDOW_MIN", "10"))


def main():
    args = [a for a in sys.argv[1:]]
    names_only = "--names-only" in args
    args = [a for a in args if a != "--names-only"]
    window_min = DEFAULT_WINDOW_MIN
    if "--window-min" in args:
        i = args.index("--window-min")
        try:
            window_min = int(args[i + 1])
        except (IndexError, ValueError):
            window_min = DEFAULT_WINDOW_MIN
        del args[i:i + 2]
    if not args:
        sys.stderr.write("lane-live-check: need <roomId>\n")
        return 2
    room = args[0]
    now_ms = time.time() * 1000
    try:
        con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """SELECT a.name AS name,
                      MIN(CASE WHEN q.status = 'running' AND q.createdAt > :cut
                               THEN q.createdAt END)                       AS run_oldest,
                      MIN(CASE WHEN q.status = 'queued' THEN q.createdAt END) AS q_oldest,
                      SUM(CASE WHEN q.status = 'queued' THEN 1 ELSE 0 END)    AS q_n,
                      MAX(CASE WHEN q.status = 'completed'
                               THEN COALESCE(q.finishedAt, q.createdAt) END)  AS last_done
                 FROM gc_execution_queue q
                 JOIN gc_room_agents a
                   ON a.agentId = q.targetAgentId AND a.roomId = q.roomId
                WHERE q.roomId = :room
                  AND COALESCE(a.removedAt, 0) = 0
             GROUP BY a.name""",
            {"room": room, "cut": now_ms - window_min * 60000},
        ).fetchall()
        con.close()
    except Exception as exc:  # UNKNOWN verdict, never "no live lanes"
        sys.stderr.write("lane-live-check: %s\n" % exc)
        return 2

    live = []
    for r in rows:
        cut = now_ms - window_min * 60000
        ts = []
        if r["run_oldest"] is not None:                 # mid-run: never nudge
            ts.append(r["run_oldest"])
        # queued-only backlog counts as live ONLY if it is demonstrably draining
        if (r["q_n"] or 0) > 0 and r["q_oldest"] is not None and r["q_oldest"] > cut:
            if r["last_done"] is not None and r["last_done"] > r["q_oldest"]:
                ts.append(r["q_oldest"])
        if ts:
            live.append((r["name"], min(ts)))
    live.sort(key=lambda t: t[1])
    for name, oldest in live:
        age = int((now_ms - oldest) / 1000)
        print(name if names_only else "%s\t%d" % (name, age))
    return 0 if live else 1


sys.exit(main())
