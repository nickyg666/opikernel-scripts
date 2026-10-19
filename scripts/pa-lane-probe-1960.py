#!/usr/bin/env python3
"""PA lane probe: distinguish WEDGED (queued, never drained, no lastError) from
DRAINED-AND-FAILED (startedAt set and/or lastError present) per (room, agent)."""
import sqlite3, time, datetime

DB = "/home/host/.hermes-web-ui/hermes-web-ui.db"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
now = int(time.time())
def ts(v):
    if not v:
        return "-"
    v = v / 1000.0 if v > 1e11 else v          # gc_execution_queue stamps are ms
    return datetime.datetime.fromtimestamp(v).strftime("%m-%d_%H:%M:%S")

q = """SELECT targetAgentName n,
              COUNT(*) enq,
              SUM(CASE WHEN startedAt IS NOT NULL THEN 1 ELSE 0 END) started,
              SUM(CASE WHEN finishedAt IS NOT NULL THEN 1 ELSE 0 END) finished,
              SUM(CASE WHEN lastError IS NOT NULL AND lastError<>'' THEN 1 ELSE 0 END) errs,
              MAX(createdAt) last_enq,
              MAX(startedAt) last_start,
              SUM(CASE WHEN startedAt IS NULL AND (lastError IS NULL OR lastError='')
                       THEN 1 ELSE 0 END) wedged_now
         FROM gc_execution_queue
        WHERE createdAt > ? GROUP BY targetAgentName ORDER BY enq DESC"""
print(f"== last 45 min (cutoff {ts(now-2700)}) ==")
for r in con.execute(q, ((now - 2700)*1000,)):
    print(f"{r['n']:>18} enq={r['enq']:<3} started={r['started']:<3} fin={r['finished']:<3} "
          f"err={r['errs']:<3} last_enq={ts(r['last_enq'])} last_start={ts(r['last_start'])} "
          f"wedged_now={r['wedged_now']}")

print("\n== distinct lastError (last 45 min, truncated) ==")
for r in con.execute(
        "SELECT targetAgentName n, lastError e, createdAt c FROM gc_execution_queue "
        "WHERE createdAt > ? AND lastError IS NOT NULL AND lastError<>'' "
        "ORDER BY createdAt DESC LIMIT 6", ((now - 2700)*1000,)):
    print(f"{r['n']:>18} {ts(r['c'])} :: {r['e'][:110].replace(chr(10),' ')}")

print("\n== per-agent chronic pile (all time) ==")
for r in con.execute(
        "SELECT targetAgentName n, COUNT(*) tot, "
        "SUM(CASE WHEN startedAt IS NULL THEN 1 ELSE 0 END) never, "
        "MAX(createdAt) last_enq FROM gc_execution_queue GROUP BY targetAgentName "
        "HAVING never>0 ORDER BY never DESC LIMIT 8"):
    print(f"{r['n']:>18} tot={r['tot']:<4} never_started={r['never']:<4} last_enq={ts(r['last_enq'])}")
