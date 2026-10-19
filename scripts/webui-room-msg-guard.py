#!/usr/bin/env python3
"""webui-room-msg-guard — keep Hermes Web-UI group-chat rooms under the
server's 'Group summary scan' limit, or EVERY mention in the room silently dies.

Root cause (proven 2026-09-19, room mti5ax1clq0zlx):
  hermes-web-ui/dist/server/index.js builds the summary scan as
      SELECT ... WHERE roomId=? AND role IN ('user','assistant') AND TRIM(content)<>''
        AND COALESCE(tool_name,'')='' AND COALESCE(tool_call_id,'')=''
        AND COALESCE(tool_calls,'[]') IN ('','[]')
        AND COALESCE(finish_reason,'') NOT IN ('tool_calls','streaming')
        <not a "[Calling tool"/"[Tool result" line>
      ORDER BY timestamp ASC, id ASC LIMIT 10001
  and throws `Group summary scan exceeded 10000 eligible messages` when the
  result set is 10001+.  processMentions runs that scan for EVERY incoming
  message, so past 10k eligible messages the room accepts posts into history
  but dispatches NOTHING: gc_execution_queue fills with status='queued' +
  startedAt NULL forever and the room looks like the agents went on strike.

What this guard does (idempotent, safe to run every 10 min):
  1. Counts eligible messages per room with the server's own predicate.
  2. If over MAX_ELIGIBLE, archives deleted rows to JSONL then deletes
     noise first (orchestrator digests, nudge lines, billing/limit errors,
     compression markers) and oldest-eligible-second until <= MAX_ELIGIBLE.
  3. Fails undelivered queue rows (queued/pending with startedAt NULL) older
     than QUEUE_MAX_AGE_MIN so a backlog cannot stampede once dispatch returns
     (dumping them to CSV first). ONLY for rooms that are actually over
     MAX_ELIGIBLE: in a room under the limit the server's dispatch is alive, so
     a >30m queued row is a real mention still in history and reaping it turns
     the row status to 'failed', which the server can never claim again
     (startExecutionQueueItem requires status='queued'). Measured 2026-09-20:
     room mti3yr2g3yjpyr (2815 eligible) had 15 still-live mentions reaped in one
     cycle while room mti5ax1clq0zlx (8712, over the 9000 trim line) legitimately
     reaped 12 already-deleted ones.
  4. Fails zombie 'running' rows: startedAt older than RUNNING_MAX_AGE_MIN AND
     the target agent has posted in that row's room AFTER startedAt (proof the
     turn progressed past its start and ended without closing the row). A turn
     with no post since startedAt is left alone — it may genuinely still work.
  5. Prints ONE summary line per room; prints nothing when nothing to do.
  6. Prints a `WEDGE <room> N stuck lane(s)` line for any (room,agent) with
     >=3 enqueues and 0 starts inside WINDOW_MIN — the per-key drain wedge the
     room-wide eligible count cannot see (see stuck_lanes()).

Never deletes the newest MAX_ELIGIBLE messages and never touches rows that
carry tool metadata (they are not counted by the server anyway).
"""
import json
import os
import sqlite3
import sys
import time

DB = os.environ.get("WEBUI_DB", "/home/host/.hermes-web-ui/hermes-web-ui.db")
ARCHIVE_DIR = os.environ.get("ROOM_GUARD_ARCHIVE", "/home/host/opikernel/state/room-guard")
QUEUE_DUMP_DIR = "/home/host/opikernel/state/queue-purge"
MAX_ELIGIBLE = int(os.environ.get("ROOM_GUARD_MAX", "9000"))
QUEUE_MAX_AGE_MIN = int(os.environ.get("ROOM_GUARD_QUEUE_MIN", "30"))
RUNNING_MAX_AGE_MIN = int(os.environ.get("ROOM_GUARD_RUNNING_MIN", "30"))
DRY_RUN = os.environ.get("ROOM_GUARD_DRY", "") not in ("", "0", "no", "false")
WINDOW_MIN = int(os.environ.get("ROOM_GUARD_WINDOW_MIN", "30"))

ELIGIBLE = """roomId = ? AND role IN ('user','assistant') AND TRIM(content) <> ''
 AND COALESCE(tool_name,'') = '' AND COALESCE(tool_call_id,'') = ''
 AND COALESCE(tool_calls,'[]') IN ('','[]')
 AND COALESCE(finish_reason,'') NOT IN ('tool_calls','streaming')"""

NOISE_PREFIXES = (
    "[orchestrator%",
    "@all continue%",
    "Billing or credits exhausted:%",
    "API call failed after 3 retries:%",
    "[COMPRESSED:%",
    "%last room output was%",
    "%idle >15m. Take ONE con%",
)


def archive(con, room, rows):
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    path = os.path.join(ARCHIVE_DIR, f"{room}-{time.strftime('%Y%m%d-%H%M%S')}-{len(rows)}rows.jsonl")
    with open(path, "w") as fh:
        for r in rows:
            fh.write(json.dumps(dict(r), default=str) + "\n")
    return path


def eligible_count(con, room):
    return con.execute(f"SELECT count(*) FROM gc_messages WHERE {ELIGIBLE}", (room,)).fetchone()[0]


def reap_undelivered(con, over_rooms, dry=False):
    cutoff = int((time.time() - QUEUE_MAX_AGE_MIN * 60) * 1000)
    allrows = [dict(r) for r in con.execute(
        "SELECT * FROM gc_execution_queue WHERE status IN ('queued','pending')"
        " AND startedAt IS NULL AND createdAt < ?", (cutoff,))]
    rows = [r for r in allrows if r.get("roomId") in over_rooms]
    skipped = len(allrows) - len(rows)
    if skipped:
        print(f"room-guard: kept {skipped} undelivered queue rows (room under {MAX_ELIGIBLE} "
              f"eligible - dispatch alive, not reaping)")
    if not rows:
        return 0
    if dry:
        print(f"room-guard: DRY would reap {len(rows)} undelivered rows in {sorted(over_rooms)}")
        return 0
    os.makedirs(QUEUE_DUMP_DIR, exist_ok=True)
    path = os.path.join(QUEUE_DUMP_DIR, f"undelivered-{time.strftime('%Y%m%d-%H%M%S')}.csv")
    with open(path, "w", newline="") as fh:
        import csv
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    ids = [r["id"] for r in rows]
    con.executemany(
        "UPDATE gc_execution_queue SET status='failed',"
        "lastError='undelivered_reaped_by_room_guard',"
        "finishedAt=CAST(strftime('%s','now') AS INTEGER)*1000 WHERE id=?",
        [(i,) for i in ids])
    return len(ids)


def reap_running(con):
    """Fail zombie 'running' rows: old AND the agent posted after startedAt."""
    cutoff = int((time.time() - RUNNING_MAX_AGE_MIN * 60) * 1000)
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM gc_execution_queue WHERE status='running'"
        " AND startedAt IS NOT NULL AND startedAt < ?"
        " AND (finishedAt IS NULL OR finishedAt = 0)"
        " AND EXISTS (SELECT 1 FROM gc_messages m"
        "             WHERE m.roomId = gc_execution_queue.roomId"
        "               AND m.senderName = gc_execution_queue.targetAgentName"
        "               AND m.timestamp > gc_execution_queue.startedAt)",
        (cutoff,))]
    if not rows:
        return 0
    os.makedirs(QUEUE_DUMP_DIR, exist_ok=True)
    path = os.path.join(QUEUE_DUMP_DIR, f"stale-running-{time.strftime('%Y%m%d-%H%M%S')}.csv")
    with open(path, "w", newline="") as fh:
        import csv
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    con.executemany(
        "UPDATE gc_execution_queue SET status='failed',"
        "lastError='stale_running_reaped_by_room_guard',"
        "finishedAt=CAST(strftime('%s','now') AS INTEGER)*1000 WHERE id=?",
        [(r["id"],) for r in rows])
    return len(rows)


def stuck_lanes(con, rooms, window_min=WINDOW_MIN, min_enq=3):
    """Per-(room,agent) wedge detector — the alarm that was missing.

    The 10k-scan guard above assumes 'room under MAX_ELIGIBLE => dispatch alive'.
    FALSIFIED 2026-09-20 (room mti5ax1clq0zlx, 8840 eligible): 7 lanes sat at
    0 started / 3-17 enqueued per 30 min while sibling lanes in the SAME room ran
    at ~100%, so dispatch was alive room-wide and dead per (room,agent) key —
    `_processingMentionQueues` in the server holds a key whose in-flight
    `replyToMention` never settles (agent client dropped mid-turn), and every
    later mention for that key is pushed in-memory and never drained: the DB row
    stays status='queued', startedAt NULL, lastError NULL (= invisible).
    A silently growing 'kept N undelivered rows' line is that symptom, not health.
    """
    cutoff = int((time.time() - window_min * 60) * 1000)
    out = []
    for room in rooms:
        rows = con.execute(
            "SELECT targetAgentName n,"
            " SUM(createdAt > ?) enq,"
            " SUM(CASE WHEN startedAt IS NOT NULL AND startedAt > ? THEN 1 ELSE 0 END) started"
            " FROM gc_execution_queue WHERE roomId = ?"
            " GROUP BY targetAgentName", (cutoff, cutoff, room)).fetchall()
        stuck = [(r["n"], r["enq"]) for r in rows if r["enq"] >= min_enq and not r["started"]]
        if stuck:
            detail = ",".join(f"{n}({e}enq/0start)" for n, e in sorted(stuck, key=lambda x: -x[1]))
            out.append(f"WEDGE {room} {len(stuck)} stuck lane(s) in last {window_min}m: {detail}")
    return out


def guard_room(con, room):
    before = eligible_count(con, room)
    deleted_noise = 0
    if before > MAX_ELIGIBLE:
        for pat in NOISE_PREFIXES:
            cur = con.execute(
                f"DELETE FROM gc_messages WHERE {ELIGIBLE} AND content LIKE ?", (room, pat))
            deleted_noise += cur.rowcount
        con.commit()
        # oldest-eligible trim, archived in chunks
        while eligible_count(con, room) > MAX_ELIGIBLE:
            batch = [dict(r) for r in con.execute(
                f"SELECT * FROM gc_messages WHERE {ELIGIBLE} ORDER BY timestamp ASC, id ASC LIMIT 500",
                (room,))]
            if not batch:
                break
            archive(con, room, batch)
            con.executemany("DELETE FROM gc_messages WHERE id = ?", [(b["id"],) for b in batch])
            con.commit()
    after = eligible_count(con, room)
    return before, after, deleted_noise


def main():
    if not os.path.exists(DB):
        print(f"room-guard: db missing {DB}", file=sys.stderr)
        return 2
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA busy_timeout=20000")
    except sqlite3.Error:
        pass
    rooms = [r[0] for r in con.execute("SELECT id FROM gc_rooms")]
    lines = []
    over_rooms = set()
    for room in rooms:
        before, after, noise = guard_room(con, room)
        if before > MAX_ELIGIBLE:
            over_rooms.add(room)
        if before != after:
            lines.append(f"{room}: eligible {before}->{after} (noise {noise}); pruned to stay under {MAX_ELIGIBLE}")
    reaped = reap_undelivered(con, over_rooms, dry=DRY_RUN)
    zombies = reap_running(con)
    wedges = stuck_lanes(con, rooms)
    con.commit()
    if reaped:
        lines.append(f"reaped {reaped} undelivered queue rows (queued/pending, startedAt NULL, >{QUEUE_MAX_AGE_MIN}m old)")
    if zombies:
        lines.append(f"reaped {zombies} zombie 'running' queue rows (>{RUNNING_MAX_AGE_MIN}m old, agent posted after startedAt)")
    lines.extend(wedges)
    for line in lines:
        print("room-guard: " + line)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
