#!/bin/bash
# gc-reap-wedged-running.sh — release per-agent dispatch slots stuck in 'running'.
#
# WHY (2026-09-19): a gc_execution_queue row that enters status='running' and never
# reaches finishedAt holds that agent's slot, so every later mention of that agent
# stays 'queued' with startedAt NULL forever. The web-ui then looks like the
# automation "is not triggering". Observed: PA row started 2026-09-18 19:16:33 was
# still 'running' 878 min later; PA's rows from 09:52/09:54 never dispatched, while
# kernel-architect's nudge row went 'running' in 1s. Reaping the head row restores
# dispatch for that agent.
#
# WHY ROOMS (2026-09-21): this script was pinned to the KERNEL room only, so a wedge
# in any other room was never swept. The Neorunner room (mti3yr2g3yjpyr) carried
# sequence 1577 (PA, 905 min) + 1652 (minecraft, 843 min) in 'running' for 15h while
# 12 queued mentions across minecraftplayer/minecraft/Neo/PA sat with startedAt NULL.
# A per-room pin makes the sweep look alive (reaped=0 every 5 min) while a whole other
# room starves — sweep every room that has a candidate row instead.
#
# Rows are NOT deleted: they are marked failed with a reason so the audit trail and
# the stale/nudge calculation stay honest.
set -euo pipefail

DB_GC="${DB_GC:-/home/host/.hermes-web-ui/hermes-web-ui.db}"
MAX_RUN_MIN="${MAX_RUN_MIN:-30}"   # a real turn never runs this long

# Explicit override wins; otherwise sweep every room holding a wedged row.
if [[ -n "${ROOM_ID:-}" ]]; then
  ROOMS="$ROOM_ID"
else
  ROOMS=$(sqlite3 "$DB_GC" "SELECT DISTINCT roomId FROM gc_execution_queue
    WHERE status='running' AND startedAt IS NOT NULL
      AND (strftime('%s','now')*1000 - startedAt)/60000.0 > $MAX_RUN_MIN;")
fi

# A silent sweep is indistinguishable from a dead cron — always emit one line.
if [[ -z "$ROOMS" ]]; then
  echo "[$(date -Is)] gc-reap-wedged-running: reaped=0 rooms=none max_run_min=$MAX_RUN_MIN"
else
for ROOM in $ROOMS; do
  reaped=$(sqlite3 "$DB_GC" "SELECT COUNT(*) FROM gc_execution_queue
    WHERE roomId='$ROOM' AND status='running'
      AND startedAt IS NOT NULL
      AND (strftime('%s','now')*1000 - startedAt)/60000.0 > $MAX_RUN_MIN;")

  sqlite3 "$DB_GC" "UPDATE gc_execution_queue
    SET status='failed',
        finishedAt=strftime('%s','now')*1000,
        lastError='wedged_running_reaped (>${MAX_RUN_MIN}min, slot released)'
    WHERE roomId='$ROOM' AND status='running'
      AND startedAt IS NOT NULL
      AND (strftime('%s','now')*1000 - startedAt)/60000.0 > $MAX_RUN_MIN;"

  echo "[$(date -Is)] gc-reap-wedged-running: reaped=$reaped room=$ROOM max_run_min=$MAX_RUN_MIN"
done
fi

# --- HOL-block guard (2026-09-22, PA) ---
# A 'queued' row with startedAt NULL that sits >90min never dispatches: the dispatcher
# drains FIFO by sequence, so one dead lane at the head blocks every later lane
# (observed: seq2438 build-engineer, dead since 09-21 15:06, HOL-blocked the whole
# room for 10h while live lanes' mentions piled up behind it with startedAt NULL).
# Reap any queued row older than STALE_QUEUE_MIN and log the count. This is safe:
# a nudge cron re-posts fresh mentions, so only stale duplicates are lost.
STALE_QUEUE_MIN="${STALE_QUEUE_MIN:-90}"
hqueued=$(sqlite3 "$DB_GC" "SELECT COUNT(*) FROM gc_execution_queue
  WHERE status='queued' AND startedAt IS NULL
    AND (strftime('%s','now')*1000 - createdAt)/60000.0 > $STALE_QUEUE_MIN;")
if [[ "$hqueued" -gt 0 ]]; then
  sqlite3 "$DB_GC" "UPDATE gc_execution_queue
    SET status='failed', finishedAt=strftime('%s','now')*1000,
        lastError='stale_queued_reaped (>${STALE_QUEUE_MIN}min never started, HOL risk)'
    WHERE status='queued' AND startedAt IS NULL
      AND (strftime('%s','now')*1000 - createdAt)/60000.0 > $STALE_QUEUE_MIN;"
fi
echo "[$(date -Is)] gc-reap-wedged-running: stale_queued_reaped=$hqueued min=$STALE_QUEUE_MIN"
