#!/usr/bin/env python3
"""Shared dead-lane predicate for group-chat rooms (public tool, 2026-09-20, PA).

WHY THIS EXISTS
    A lane goes dead when its (roomId, agentId) drain key is stuck: the web-ui
    keeps _processingMentionQueues[room\\0agentId] latched, so every later
    @mention for that key is pushed in-memory and never shifted -> the row stays
    status='queued', startedAt NULL, lastError NULL, forever.  Agents that are
    delivering fine in the SAME room keep completing normally, so the room looks
    healthy while individual lanes are black holes.

    Every whip/digest that @mentions such a lane makes it worse: measured 25
    fresh undelivered rows in 30 min across build-engineer / powervr-monkey /
    Backlog-worker2 / kernel-architect.  Quarantine the lane, escalate once.

    This is the ONE predicate; group-orchestrator.sh and kernel-room-nudge.sh
    both call it so the two whip paths can never disagree.

USAGE
    lane-wedge-check.py --room <roomId> --all            # name<TAB>why, one per line
    lane-wedge-check.py --room <roomId> --names-only     # just the names
    lane-wedge-check.py --room <roomId> --any A B C      # rc=0 if any of A/B/C wedged

    rc: 0 = at least one wedged lane found, 1 = none, 2 = usage/DB error OR the
    twin-identity guard below fired (DEGRADED).  Callers must never read rc=2 as
    "no wedged lanes" — scripts/wedge-quarantine.sh owns that contract.

TUNABLES (env)
    WEDGE_WINDOW_MIN (180)  window the per-lane row stats are counted over
    WEDGE_MIN_REAPS   (4)    >= this many reaped rows + 0 completions = wedged
    WEDGE_MIN_QUEUED  (12)   or >= this many undrained rows + 0 completions = wedged
                             (catches the case where the REAPER is stuck too, so
                              rows sit at status='queued' and never even fail)
    WEDGE_PILE        (40)   or >= this many still-queued rows = wedged
    WEDGE_DB                 override the sqlite path
"""
import os
import sqlite3
import sys
import time

DB = os.environ.get("WEDGE_DB", "/home/host/.hermes-web-ui/hermes-web-ui.db")
WINDOW_MIN = int(os.environ.get("WEDGE_WINDOW_MIN", "180"))
MIN_REAPS = int(os.environ.get("WEDGE_MIN_REAPS", "4"))
MIN_QUEUED = int(os.environ.get("WEDGE_MIN_QUEUED", "12"))
PILE = int(os.environ.get("WEDGE_PILE", "40"))


def _stats(con, room, name, start_ms):
    """Windowed per-lane counters. Every aggregate is coalesced: `lastError LIKE ...`
    is NULL for queued rows, so sum() returns NULL (not 0) when a lane's only rows
    are undrained — which is exactly the reaper-stopped case this tool exists for.
    Unguarded, that NULL raised TypeError, the exception was swallowed by main()'s
    handler, rc=2 came back, and BOTH whips lost their circuit breaker entirely
    (orchestrator rows reappeared for wedged lanes at 20:37/20:38, 2026-09-20)."""
    return con.execute(
        """SELECT coalesce(sum(status='completed'),0)         AS done,
                  coalesce(sum(lastError LIKE '%reaped%'),0) AS reaped,
                  coalesce(sum(status='queued'),0)           AS queued,
                  count(*)                                   AS total,
                  min(createdAt)                             AS first_ms
             FROM gc_execution_queue
            WHERE roomId=? AND targetAgentName=? AND createdAt>?""",
        (room, name, start_ms)).fetchone()


def twins(room):
    """Two classes of name->agentId ambiguity in ONE room; only one is fatal.

    The stats above group by NAME, but the web-ui drain guard is keyed
    room\\0agentId.  Splitting the two cases is the whole point (measured against
    the live DB, 2026-09-20):

    * HARD — the name owns >1 LIVE roster agentId (gc_room_agents removedAt=0) in
      this room.  Two addressable drain keys share one name, so the healthy twin's
      completion masks the stuck twin's zero-completion wedge (max(finishedAt)
      lands on the live one) and the lane reads healthy forever.  Not something to
      paper over with a max(): this returns rc=2 DEGRADED and both whips fall back
      to the last known-good list.  ZERO such cases exist today; if one appears it
      is a routing decision for @the-human, not a silent merge.
    * SOFT — the name carries extra RETIRED agentIds in this room's queue history
      (agent re-created; the ghosts hold 1-4 failed rows each).  They cannot
      receive a mention, so they are not a masking hazard and must NOT degrade the
      predicate — blocking on them would freeze the breaker at its last list
      forever.  Reported as a NOTE on stderr only.

    Also measured: gc_room_agents is per-ROOM ('PA' holds mu5nn47weuqmrf here and
    mu7devla138szb in mti3yr2g3yjpyr), so the same name in a DIFFERENT room is
    neither class and must block nothing.
    """
    roster = {}
    con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
    try:
        for nm, aid in con.execute(
                """SELECT DISTINCT name, agentId FROM gc_room_agents
                    WHERE roomId=? AND removedAt=0 AND name IS NOT NULL
                      AND agentId IS NOT NULL""", (room,)):
            roster.setdefault(nm, set()).add(aid)
    except sqlite3.Error:
        pass
    live, retired = [], []
    for nm, aid in con.execute(
            """SELECT DISTINCT targetAgentName, targetAgentId FROM gc_execution_queue
                WHERE roomId=? AND targetAgentName IS NOT NULL
                  AND targetAgentId IS NOT NULL""", (room,)):
        ids = roster.get(nm, set())
        (live if aid in ids else retired).append((nm, aid))
    lmap, rmap = {}, {}
    for nm, aid in live:
        lmap.setdefault(nm, set()).add(aid)
    for nm, aid in retired:
        rmap.setdefault(nm, set()).add(aid)
    hard = [(n, sorted(v)) for n, v in sorted(lmap.items()) if len(v) > 1]
    # a retired id is only noise when the name is still addressable at all
    soft = [(n, sorted(rmap[n])) for n in sorted(rmap) if n in roster]
    return hard, soft


def wedged(room):
    """[{name, why}] for every dead lane in `room`; [] when the drain is healthy."""
    now_ms = time.time() * 1000
    win_start = now_ms - WINDOW_MIN * 60000
    con = sqlite3.connect(DB)
    names = [r[0] for r in con.execute(
        """SELECT DISTINCT targetAgentName FROM gc_execution_queue
            WHERE roomId=? AND targetAgentName IS NOT NULL""", (room,))]
    last_done = dict(con.execute(
        """SELECT targetAgentName, max(finishedAt) FROM gc_execution_queue
            WHERE roomId=? AND status='completed' AND targetAgentName IS NOT NULL
         GROUP BY targetAgentName""", (room,)))
    out = []
    for name in names:
        done, reaped, queued, total, first = _stats(con, room, name, win_start)
        if done == 0:
            # Never let the clock decide a lane's verdict. Re-stat from this lane's
            # last completion (or its whole history when it has never completed):
            #  * A quarantined lane receives no new rows, so a fixed window aged its
            #    own evidence out and read it healthy again (20:36: quarantined 3 -> 2
            #    while still dead).
            #  * The inverse false positive is worse: a row can sit queued for hours
            #    and then complete, so its createdAt falls OUTSIDE the window while
            #    its finishedAt is now — `done` read 0 and the whips kept suppressing
            #    a lane that had just delivered (Backlog-worker2: row created 17:52:04,
            #    finished 20:52:56, still reported "0 completed since 18:04").
            # Only a completion AFTER the anchor clears a lane; a live drain always
            # produces one, so a recent completion leaves this window empty = healthy.
            ld = last_done.get(name)
            start = (ld + 1) if ld is not None else 0
            done, reaped, queued, total, first = _stats(con, room, name, start)
        if first is None:
            continue
        since = time.strftime('%H:%M', time.localtime(first / 1000))
        if done == 0 and reaped >= MIN_REAPS:
            out.append((name, "%d reaped / %d rows, 0 completed since %s" % (
                reaped, total, since)))
        elif done == 0 and queued >= MIN_QUEUED:
            out.append((name, "%d mentions undrained, 0 completed since %s" % (
                queued, since)))
        elif queued >= PILE:
            out.append((name, "%d mentions undrained (queued, no completions)" % queued))
    return out


def main(argv):
    room = None
    mode = None
    names = []
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--room":
            i += 1
            room = argv[i] if i < len(argv) else None
        elif a == "--all":
            mode = "all"
        elif a == "--names-only":
            mode = "names"
        elif a == "--any":
            mode, names = "any", argv[i + 1:]
            break
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            print("unknown arg: %s" % a, file=sys.stderr)
            return 2
        i += 1
    if not room or not mode:
        print(__doc__)
        return 2
    try:                                        # twin identity -> DEGRADED, not silence
        hard, soft = twins(room)
    except Exception as e:
        print("lane-wedge-check: twin check error: %s" % e, file=sys.stderr)
        return 2
    for n, ids in soft:                         # retired ids: NOTE only, never fatal
        print("lane-wedge-check: note: %s carries %d retired agentId(s) in %s (%s) — "
              "not addressable, not degrading the predicate"
              % (n, len(ids), room, ",".join(ids)), file=sys.stderr)
    if hard:
        for n, ids in hard:
            print("lane-wedge-check: DEGRADED twin identity: name=%s owns %d LIVE agentIds "
                  "in room %s (%s) — name-keyed stats would mask a stuck drain key"
                  % (n, len(ids), room, ",".join(ids)), file=sys.stderr)
        return 2
    try:
        bad = wedged(room)
    except Exception as e:                      # DB busy/locked -> never wedge the caller
        print("lane-wedge-check: db error: %s" % e, file=sys.stderr)
        return 2
    if mode == "all":
        for n, why in bad:
            print("%s\t%s" % (n, why))
        return 0 if bad else 1
    if mode == "names":
        for n, _ in bad:
            print(n)
        return 0 if bad else 1
    hit = [n for n, _ in bad if n in set(names)]
    for n in hit:
        print(n)
    return 0 if hit else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
