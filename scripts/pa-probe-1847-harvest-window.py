#!/usr/bin/env python3
"""PA probe 18:47: is there a harvest WINDOW? For every row that ever STARTED in this
room, measure startedAt-createdAt (how fresh a mention must be to get claimed) and
bucket the still-queued rows by age. If started rows are always young and queued rows
are all old, the drain only harvests fresh mentions -> old queued rows are orphans.
Read-only, room-scoped.
"""
import sqlite3, time, collections

DB = "/home/host/.hermes-web-ui/hermes-web-ui.db"
ROOM = "mti5ax1clq0zlx"
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
c.row_factory = sqlite3.Row
now_ms = int(time.time() * 1000)
print("now_ms=%d  now=%s" % (now_ms, time.strftime("%H:%M:%S")))

# 1. freshness at claim time for rows that started
st = c.execute("""
    select targetAgentName nm, createdAt, startedAt, finishedAt, status
    from gc_execution_queue
    where roomId=? and startedAt is not null
    order by startedAt desc limit 400
""", (ROOM,)).fetchall()
print("rows_with_startedAt(total recent)=%d" % len(st))
ages = [(r["startedAt"] - r["createdAt"]) / 1000.0 for r in st if r["createdAt"] and r["startedAt"]]
if ages:
    ages.sort()
    print("CLAIM FRESHNESS (startedAt-createdAt sec): min=%.1f p50=%.1f p90=%.1f max=%.1f"
          % (ages[0], ages[len(ages)//2], ages[int(len(ages)*0.9)], ages[-1]))
    buckets = collections.Counter()
    for a in ages:
        b = "<30s" if a < 30 else "30-60s" if a < 60 else "1-5m" if a < 300 else "5-30m" if a < 1800 else ">30m"
        buckets[b] += 1
    print("freshness_hist:", dict(buckets))

# 2. newest 10 claimed rows vs the queued orphans
print("\n--- newest 10 CLAIMED ---")
for r in st[:10]:
    print("  %-18s created=%d claimed=+%.0fs status=%s" % (r["nm"], r["createdAt"], (r["startedAt"]-r["createdAt"])/1000.0, r["status"]))
print("\n--- oldest 6 STILL QUEUED (orphans?) ---")
q = c.execute("""
    select targetAgentName nm, createdAt, messageId from gc_execution_queue
    where roomId=? and status='queued' order by createdAt asc limit 6
""", (ROOM,)).fetchall()
for r in q:
    print("  %-18s age_min=%.1f msg=%s" % (r["nm"], (now_ms - r["createdAt"])/60000.0, r["messageId"]))

# 3. how many started rows happened in the last 20 min, and their freshness
cut = now_ms - 20*60*1000
recent = [r for r in st if r["startedAt"] >= cut]
print("\nstarted_in_last_20min=%d" % len(recent))
if recent:
    ra = [(r["startedAt"]-r["createdAt"])/1000.0 for r in recent]
    print("  their freshness: min=%.1f max=%.1f p50=%.1f" % (min(ra), max(ra), sorted(ra)[len(ra)//2]))

# 4. status totals for the room, all time
print("\nstatus_totals:", dict(c.execute("select status,count(*) from gc_execution_queue where roomId=? group by 1", (ROOM,)).fetchall()))
