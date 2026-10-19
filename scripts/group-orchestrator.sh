#!/bin/bash
# /home/host/opikernel/scripts/group-orchestrator.sh
# Churn guard + idle detector + board health + group-mode for ALL rooms.
# Cron: */1 * * * * /home/host/opikernel/scripts/group-orchestrator.sh
# Group mode: loops every room in gc_rooms, never solo (ROOM_ID env still supported for single-room override).
set -e
export ROOM_ID="${ROOM_ID:-}"   # if empty -> ALL rooms
# PA 2026-09-20: this is the KERNEL orchestrator. Scope it to the kernel room so no
# invoker (/etc/crontab */1, launcher, manual) can nudge a different team's room.
# Why it matters: in the Neorunner room mti3yr2g3yjpyr the room's ONLY member identity is
# the human (userName 'admin', authUserId 1), so gc-post --as orchestrator landed as a
# senderType='member' post. The detector's attendance gate ("a non-agent member posted
# within ROOM_HUMAN_MIN") then read a fresh human post every ~66s — the orchestrator's own
# nudges kept its target 'attended' and it looped forever (108 rows/2h; 8,748 historically).
# ORCH_ROOMS is the detector's authoritative allowlist; it propagates to the child detector.
export ORCH_ROOMS="${ORCH_ROOMS:-mti5ax1clq0zlx}"
export DB_GC="${DB_GC:-/home/host/.hermes-web-ui/hermes-web-ui.db}"
export DB="${DB:-/home/host/.hermes/state.db}"
export LOG="${LOG:-/home/host/opikernel/logs/group-orchestrator.log}"
export IDLE_MIN="${IDLE_MIN:-7}"
export BLOCK_AGE_MIN="${BLOCK_AGE_MIN:-6}"
# where to also drop agentic-pool files (used by yolo nudges)
export POOL_DIR="${POOL_DIR:-/home/host/opikernel/agentic-pool}"
export POST_STATE="${POST_STATE:-/home/host/opikernel/state/orchestrator-post-state.json}"
mkdir -p "$(dirname "$LOG")" "$POOL_DIR"
exec >> "$LOG" 2>&1

# Single-instance guard (2026-09-18). Two overlapping ticks both read "digest
# changed", both post, and every stale agent gets dispatched twice — the nudge
# batch (<=4 mentions) and the digest (@all stale) can both fire inside ONE tick
# anyway, which is the double-dispatch Nick saw at 15:09:04/15:09:05.
LOCK="${ORCH_LOCK:-/home/host/opikernel/state/group-orchestrator.lock}"
mkdir -p "$(dirname "$LOCK")"
exec 8>"$LOCK"
if ! flock -n 8; then
  echo "=== $(date -Is) tick SKIPPED: another orchestrator instance holds $LOCK ==="
  exit 0
fi
while true; do
echo "=== $(date -Is) orchestrator tick (group) ==="

# 1. Board health check + golden recovery (shared across all rooms)
BOARD_DOWN=0
timeout 3 ping -c 1 -W 2 192.168.0.151 >/dev/null 2>&1 || BOARD_DOWN=1
if [ $BOARD_DOWN -eq 0 ]; then
  timeout 5 ssh -o ConnectTimeout=3 -o BatchMode=yes orangepi@192.168.0.151 echo ok >/dev/null 2>&1 || BOARD_DOWN=1
else
  :
fi

# Board answered -> whatever we were cycling for is over; reset the wear counter
# so the backoff above does not stay latched forever.
if [ $BOARD_DOWN -eq 0 ]; then
  SF=/home/host/opikernel/state/board_151.json
  if [ -f "$SF" ]; then
    python3 -c "
import json
d=json.load(open('$SF'))
if d.get('cycles_no_recovery'):
    d['cycles_no_recovery']=0
    json.dump(d, open('$SF','w'), indent=2)
" 2>/dev/null || true
  fi
fi

if [ $BOARD_DOWN -eq 1 ]; then
  STATE_FILE=/home/host/opikernel/state/board_151.json
  NOW=$(date +%s)
  if [ ! -f "$STATE_FILE" ]; then
    echo '{"stage":0,"last_attempt":0,"attempts":0,"history":[]}' > "$STATE_FILE"
  fi
  STAGE=$(python3 -c "import json; d=json.load(open('$STATE_FILE')); print(d.get('stage',0))")
  LAST=$(python3 -c "import json; d=json.load(open('$STATE_FILE')); print(d.get('last_attempt',0))")
  ATTEMPTS=$(python3 -c "import json; d=json.load(open('$STATE_FILE')); print(d.get('attempts',0))")
  NO_RECOVERY=$(python3 -c "import json; d=json.load(open('$STATE_FILE')); print(d.get('cycles_no_recovery',0))" 2>/dev/null || echo 0)

  # --- single-writer guard (2026-09-18) ------------------------------------
  # This branch exists to power-cycle a board that cannot answer SSH. But a board
  # that is mid-boot or mid-transfer ALSO cannot answer SSH, so the loop happily
  # cut power 190 times — landing in the middle of transfers (the source of
  # "FDT_ERR_BADMAGIC" / "stuck at the U-Boot prompt") and wearing the SD card.
  # While a lease is held, the lease owner owns power + serial, and we stay off it.
  LEASE_OK=1
  HOLDER=$(/home/host/opikernel/scripts/board-lease.sh status 2>/dev/null || echo "no active lease")
  case "$HOLDER" in
    "lease ACTIVE"*)
      LEASE_OK=0
      echo "  board .151 down but $HOLDER — not touching power/serial"
      ;;
  esac

  # Storage protection: after BOARD_CYCLE_MAX unproductive cycles, back off from
  # 10 min to an hour. A board that failed 5 power cycles will not be fixed by #6.
  COOLDOWN=600
  if [ "${NO_RECOVERY:-0}" -ge "${BOARD_CYCLE_MAX:-5}" ]; then
    COOLDOWN="${BOARD_CYCLE_BACKOFF:-3600}"
    echo "  board .151: $NO_RECOVERY unproductive cycles -> backing off to ${COOLDOWN}s between attempts"
  fi

  ELAPSED=$((NOW - LAST))
  if [ "$LEASE_OK" = "0" ]; then
    :
  elif [ $ELAPSED -gt $COOLDOWN ]; then
    NEXT_STAGE=$((STAGE + 1))
    if [ $NEXT_STAGE -ge 4 ]; then NEXT_STAGE=1; fi
    ATTEMPT_NUM=$((ATTEMPTS + 1))
    case $NEXT_STAGE in
      1)
        echo "  board .151 down (attempt $ATTEMPT_NUM): stage 1 = smartplug cycle"
        timeout 30 python3.14 /home/host/smartplug.py cycle opiz3w 2>&1 | head -n 3 || true
        ;;
      2)
        echo "  board .151 still down (attempt $ATTEMPT_NUM): stage 2 = U-Boot interrupt + booti safe DTB"
        timeout 90 /home/host/opikernel/scripts/board-golden-recovery.sh --skip-power 2>&1 | head -n 10 || true
        ;;
      3)
        echo "  board .151 still down (attempt $ATTEMPT_NUM): stage 3 = smartplug cycle again"
        timeout 30 python3.14 /home/host/smartplug.py cycle opiz3w 2>&1 | head -n 3 || true
        ;;
    esac
    python3 -c "
import json; d=json.load(open('$STATE_FILE'))
d['stage']=$NEXT_STAGE; d['last_attempt']=$NOW; d['attempts']=$ATTEMPT_NUM
d['cycles_no_recovery']=d.get('cycles_no_recovery',0)+1
d['history']=d.get('history',[])[-9:] + [{'t':$NOW,'stage':$NEXT_STAGE,'attempt':$ATTEMPT_NUM}]
json.dump(d, open('$STATE_FILE','w'), indent=2)
" || true
  else
    echo "  board .151 still unreachable ($((ELAPSED/60))min since last attempt, stage=$STAGE, attempts=$ATTEMPTS)"
  fi
fi

# 2. Auto-clear stuck handoff chains (max_depth) for every room
python3 <<'PY'
import sqlite3
con = sqlite3.connect("/home/host/.hermes-web-ui/hermes-web-ui.db")
cur = con.cursor()
rows = list(cur.execute("SELECT roomId, chainId, currentDepth, maxDepth FROM gc_handoff_chains WHERE status='stopped' AND stopReason='max_depth'"))
for roomId, chainId, curDepth, maxDepth in rows:
    print(f"  [auto-clear] room {roomId[:12]} chain {chainId[:16]} depth {curDepth}/{maxDepth}")
    cur.execute("DELETE FROM gc_handoff_chains WHERE chainId=?", (chainId,))
con.commit()
if not rows:
    print("  [chains] none stuck")
PY

# 3a. Requeue stale pending items (gateway restart left them orphaned — status='pending' but createdAt older than 60s)
# 2026-09-19: this used to bump createdAt on EVERY pending row, with no room filter and no
# deliverability check. That kept a dead Sep-18 startup broadcast ('@all UNBLOCK', mentions='[]')
# alive forever: 6 rows re-aged every tick, so they never aged out and never dispatched, and
# every purge of "startedAt IS NULL and old" missed them. A row whose message carries no
# participantIds can never be delivered — delete it instead of re-aging it.
python3 << 'PYREQ'
import sqlite3, time
try:
    con = sqlite3.connect("/home/host/.hermes-web-ui/hermes-web-ui.db")
    now = int(time.time() * 1000)
    dead = con.execute("""
        SELECT COUNT(*) FROM gc_execution_queue q JOIN gc_messages m ON m.id=q.messageId
        WHERE q.status='pending' AND q.createdAt < ? - 60000
          AND (m.mentions IS NULL OR m.mentions IN ('', '[]'))
    """, (now,)).fetchone()[0]
    if dead:
        con.execute("""
            DELETE FROM gc_execution_queue WHERE id IN (
              SELECT q.id FROM gc_execution_queue q JOIN gc_messages m ON m.id=q.messageId
              WHERE q.status='pending' AND q.createdAt < ? - 60000
                AND (m.mentions IS NULL OR m.mentions IN ('', '[]')))
        """, (now,))
        con.commit()
        print(f"  [requeue] dropped {dead} undeliverable pending rows (message has no mentions)")
    stale = list(con.execute("""
        SELECT q.id FROM gc_execution_queue q JOIN gc_messages m ON m.id=q.messageId
        WHERE q.status='pending' AND q.createdAt < ? - 60000
          AND m.mentions IS NOT NULL AND m.mentions NOT IN ('', '[]')
    """, (now,)))
    if stale:
        con.execute("""
            UPDATE gc_execution_queue SET createdAt=? WHERE id IN (
              SELECT q.id FROM gc_execution_queue q JOIN gc_messages m ON m.id=q.messageId
              WHERE q.status='pending' AND q.createdAt < ? - 60000
                AND m.mentions IS NOT NULL AND m.mentions NOT IN ('', '[]'))
        """, (now, now))
        con.commit()
        print(f"  [requeue] bumped {len(stale)} deliverable pending queue items")
    else:
        print("  [requeue] none")
except Exception as e:
    print(f"  [requeue] skip: {e}")
PYREQ

# 3. Run detector (multi-room)
timeout 10 /home/host/.hermes/hermes-agent/venv/bin/python3 /home/host/opikernel/scripts/group_orchestrator_detect.py || {
  echo "detect rc=$?"
  exit 0
}

# 4. Room resolver + nudges
# Determine rooms to process: if ROOM_ID set -> that one room, else ALL from detector output
if [ -n "$ROOM_ID" ]; then
  ROOMS="$ROOM_ID"
else
  ROOMS=$(python3 -c "import json; d=json.load(open('/home/host/opikernel/state/orchestrator.json')); print(' '.join(d.get('rooms', {}).keys()))" 2>/dev/null || echo "")
fi
echo "rooms: ${ROOMS:-<none>}"
# Rooms the detector deliberately skipped (unattended / excluded). Printing this
# matters: without it a silent room looks identical to a room that has no stale
# agents, which is how the Neorunner mis-target went unnoticed for 8,748 nudges.
SKIPPED=$(python3 -c "
import json
d=json.load(open('/home/host/opikernel/state/orchestrator.json'))
s=d.get('skipped',{})
print(' '.join(f'{k}:{v.replace(chr(32),chr(95))}' for k,v in s.items()))
" 2>/dev/null || echo "")
[ -n "$SKIPPED" ] && echo "skipped-rooms: $SKIPPED"

# Nudge pacing (added 2026-09-18). Both guards exist because this script fires
# EVERY MINUTE and the nudge was fire-and-forget: a role whose staleness never
# cleared got a brand-new full YOLO agent session every 60s, forever
# (8,277 nudges logged, 8 concurrent sessions observed). Two brakes:
#   * per-role cooldown — the detector's threshold is idle>15min, so re-nudging a
#     role inside NUDGE_COOLDOWN_MIN minutes cannot change the outcome.
#   * global concurrency cap — bounds the blast radius regardless of room count.
NUDGE_STATE="${NUDGE_STATE:-/home/host/opikernel/state/nudge-state.json}"
NUDGE_COOLDOWN_MIN="${NUDGE_COOLDOWN_MIN:-10}"
NUDGE_BATCH_MIN="${NUDGE_BATCH_MIN:-5}"
NUDGE_BATCH_STATE="${NUDGE_BATCH_STATE:-/home/host/opikernel/state/orchestrator-nudge-batch.json}"
MAX_YOLO="${MAX_YOLO:-4}"
mkdir -p "$(dirname "$NUDGE_STATE")"

batch_allowed() {   # $1=room ; rc 0 = a nudge batch may be posted this tick
  python3 - "$NUDGE_BATCH_STATE" "$1" "$NUDGE_BATCH_MIN" <<'PYX' 2>/dev/null
import json, os, sys, time
p, key, cool = sys.argv[1], sys.argv[2], int(sys.argv[3]) * 60
try:
    d = json.load(open(p))
except Exception:
    d = {}
if (time.time() - d.get(key, 0)) < cool:
    sys.exit(1)
d[key] = time.time()
tmp = p + ".tmp"
json.dump(d, open(tmp, "w"))
os.replace(tmp, p)
sys.exit(0)
PYX
}

# Read-only mirror of the digest dedupe further down: rc 0 = the digest is due
# this tick (stale set changed, or heartbeat cooldown expired) and will therefore
# @mention EVERY stale worker. Used to suppress the separate <=4-mention nudge
# batch — without this both fire in the same tick and 4 agents get dispatched
# twice, back to back (observed 2026-09-18 15:09:04 + 15:09:05).
digest_will_post() {  # $1=room $2=key
  python3 - "$POST_STATE" "$2" "${ORCH_POST_COOLDOWN_MIN:-15}" <<'PYD' 2>/dev/null
import hashlib, json, sys, time
p, key, cool = sys.argv[1], sys.argv[2], int(sys.argv[3]) * 60
k = hashlib.sha1(key.encode()).hexdigest()[:16]
try:
    d = json.load(open(p))
except Exception:
    d = {}
last = d.get(key.split("|", 1)[0], {})
sys.exit(1 if (last.get("hash") == k and (time.time() - last.get("ts", 0)) < cool) else 0)
PYD
}

nudge_allowed() {   # $1=room $2=role ; rc 0 = allowed
  python3 - "$NUDGE_STATE" "$1|$2" "$NUDGE_COOLDOWN_MIN" <<'PYX' 2>/dev/null
import json, sys, time
p, key, cool = sys.argv[1], sys.argv[2], int(sys.argv[3]) * 60
try:
    d = json.load(open(p))
except Exception:
    d = {}
sys.exit(0 if (time.time() - d.get(key, 0)) >= cool else 1)
PYX
}

mark_nudged() {     # $1=room $2=role
  python3 - "$NUDGE_STATE" "$1|$2" <<'PYX' 2>/dev/null
import json, os, sys, time
p, key = sys.argv[1], sys.argv[2]
try:
    d = json.load(open(p))
except Exception:
    d = {}
d[key] = time.time()
tmp = p + ".tmp"
json.dump(d, open(tmp, "w"))
os.replace(tmp, p)
PYX
}

# --- provider-failure fast retry (the-human, 2026-09-18) ---------------------
# "we need that check to kick off once a minute instead of the current interval
#  especially if the provider errors for billing. routing will handle it for you,
#  just retry."
# A billing/provider failure is NOT idleness — the agent never got to run, so the
# 10-min per-role nudge cooldown and the 5-min batch cooldown would just park a
# dead agent for 10 minutes. When a role's NEWEST message is a provider failure,
# both cooldowns are bypassed and the role is re-mentioned on the next tick (60s).
# Bounded by MAX_YOLO, so this can never fork-bomb.
PROVIDER_ERR_RE='(billing, credits, or account entitlement|Add credits or update billing|Error from provider|\[40[34]\]|\[429\]|\[502\]|rate limit|quota exceeded|does not exist\. \(HTTP|Stream ended before producing|provider .* (error|exhausted))'
provider_error() {  # $1=room $2=role ; rc 0 = newest output is a provider failure
  python3 - "$DB_GC" "$1" "$2" "$PROVIDER_ERR_RE" <<'PYE' 2>/dev/null
import re, sqlite3, sys
db, room, role, pat = sys.argv[1:5]
rx = re.compile(pat, re.I)
try:
    con = sqlite3.connect(db)
    row = con.execute(
        "SELECT content FROM gc_messages WHERE roomId=? AND senderName=? "
        "AND senderType!='user' ORDER BY timestamp DESC LIMIT 1",
        (room, role)).fetchone()
except Exception:
    sys.exit(1)
txt = (row[0] if row else "") or ""
# Guards: the text must be a SHORT status line, not a long report that merely
# mentions a 403 somewhere. Provider failures arrive as short error blobs.
sys.exit(0 if txt and len(txt) < 4000 and rx.search(txt) else 1)
PYE
}

# Prune nudge-state keys belonging to rooms we no longer process. Without this the
# state file grows forever and, worse, keeps the cooldown latched for the WRONG
# room — the dead Neorunner room held all 6 cooldown keys while the live room got
# zero nudges.
python3 - "$NUDGE_STATE" "$ROOMS" <<'PYX' 2>/dev/null || true
import json, os, sys
p, rl = sys.argv[1], set(sys.argv[2].split())
try:
    d = json.load(open(p))
except Exception:
    sys.exit(0)
keep = {k: v for k, v in d.items() if k.split("|", 1)[0] in rl}
if keep != d:
    tmp = p + ".tmp"
    json.dump(keep, open(tmp, "w"))
    os.replace(tmp, p)
    print(f"  pruned nudge-state: {len(d)-len(keep)} key(s) for unprocessed rooms", file=sys.stderr)
PYX

for ROOM in $ROOMS; do
  # Newline-separated names — agent names may contain spaces (e.g. "py specialist",
  # "Workflow organizer"); word-splitting them produced garbage roles and bogus
  # yolo nudge sessions. One name per line + `while IFS= read -r`. Fixed 2026-09-18.
  STALE=$(timeout 5 python3 -c "import json; d=json.load(open('/home/host/opikernel/state/orchestrator.json')); print('\n'.join(a for a,_,_ in d.get('rooms', {}).get('$ROOM', {}).get('stale', [])))" 2>/dev/null || echo "")
  BLOCK=$(timeout 5 python3 -c "import json; d=json.load(open('/home/host/opikernel/state/orchestrator.json')); print('\n'.join(a for a,_,_ in d.get('rooms', {}).get('$ROOM', {}).get('blockers', [])))" 2>/dev/null || echo "")
  STALE_FLAT=$(printf '%s' "$STALE" | tr '\n' ' ')
  BLOCK_FLAT=$(printf '%s' "$BLOCK" | tr '\n' ' ')
  echo "[$ROOM] stale=[$STALE_FLAT] blockers=[$BLOCK_FLAT]"

  # --- per-room nudge accumulators (2026-09-20) --------------------------------
  # NUDGED/RETRY_NUDGED were reset only INSIDE the `[ -n "$STALE" ] && CAN_NUDGE
  # && !digest_will_post` branch below. A room with no dispatchable stale role
  # skips that branch, so the PREVIOUS room's batch survived and was re-posted
  # into THIS room: gc-post then rejected the foreign names, killed the whole
  # post, and fell back to a local yolo spawn of roles that do not exist here.
  # Measured: 715 MENTION REJECTED (612 of them KernelDev-GPU's own workers
  # rejected while posting to the Neorunner room) + 284 fallback spawns.
  # Reset unconditionally, once per room, BEFORE anything reads them.
  NUDGED=""
  RETRY_NUDGED=""

  # --- stale-set sanitation (2026-09-18) ---------------------------------------
  # The detector counts every row in gc_room_agents, including 'default' — a UI
  # placeholder agent that was REMOVED from the room (removedAt=1788723810203).
  # It can never be dispatched (server: getRoomAgents = ... AND removedAt = 0) and
  # nothing ever posts as it, so it is permanently "stale": it kept the digest
  # non-empty on every tick ("stale=none(1 unmentionable)") and forced a post
  # every 15 min about a role that does not exist. Drop anything that cannot be
  # dispatched BEFORE it reaches the nudge/digest logic, so an empty stale set
  # means a quiet room instead of phantom idleness.
  ROSTER=$(sqlite3 "$DB_GC" "SELECT name FROM gc_room_agents WHERE roomId='$ROOM' AND removedAt=0;" 2>/dev/null | sort)
  roster_has() { printf '%s\n' "$ROSTER" | grep -Fxq -- "$1"; }
  KEEP=""
  while IFS= read -r role; do
    [ -z "$role" ] && continue
    case ":${NUDGE_DENY:-default:none:n/a:minecraft:}:" in *":$role:"*)
      echo "  [$ROOM] stale-drop: '${role}' (placeholder/non-agent role)"
      continue ;;
    esac
    if ! roster_has "$role"; then
      echo "  [$ROOM] stale-drop: '${role}' (not in gc_room_agents removedAt=0 — cannot be dispatched)"
      continue
    fi
    KEEP="${KEEP}${KEEP:+
}${role}"
  done <<< "$STALE"
  STALE="$KEEP"
  STALE_FLAT=$(printf '%s' "$STALE" | tr '\n' ' ')

  # --- dead-lane quarantine (2026-09-20, PA) ----------------------------------
  # build-engineer / powervr-monkey / kernel-architect / Backlog-worker2 have 0
  # completed mentions in 3 h while their rows pile up (11+ reaped, 25-54 still
  # queued). Their per-(room,agent) drain key is stuck, so EVERY @mention this
  # tick enqueues a row that is never delivered - measured 25 fresh undelivered
  # rows in the last 30 min, all created by this script's own digest. Keep such
  # lanes in the digest TEXT (visibility + accountability for the human) but out
  # of every STRUCTURED mention, or the whip feeds a black hole and the room
  # reads a stuck drain as laziness. Predicate shared with kernel-room-nudge.sh
  # via scripts/lane-wedge-check.py so the two whip paths cannot disagree.
  WEDGED=$(ROOM_ID="$ROOM" WEDGE_ROOM="$ROOM" WEDGE_DB="$DB_GC" WEDGE_MODE=--names-only \
    WEDGE_TOOL="${WEDGE_TOOL:-/home/host/opikernel/scripts/lane-wedge-check.py}" \
    WEDGE_LAST="${WEDGE_LAST:-/home/host/opikernel/state/wedge-last.names.txt}" \
    WEDGE_TIMEOUT=6 bash /home/host/opikernel/scripts/wedge-quarantine.sh)
  lane_wedged() { [ -n "$WEDGED" ] && printf '%s\n' "$WEDGED" | grep -Fxq -- "$1"; }
  if [ -n "$WEDGED" ]; then
    echo "  [$ROOM] wedged lanes (mentions suppressed): $(printf '%s' "$WEDGED" | tr '\n' ' ')"
  fi

  # --- live-row mention gate (PA, 2026-09-20 23:3x) --------------------------
  # staleness here keys on the lane's last ROOM MESSAGE, so a lane that is mid-run
  # (or whose mention is already queued) reads "silent" every tick and is mentioned
  # again -> the digest itself minted the pile it then complained about. Measured
  # room-scoped off gc_execution_queue: powervr-monkey 1 running + 4 queued
  # (333s/269s/206s/15s), backlog-worker1 1+3, build-engineer 1+2 — one new row per
  # digest, same lagging lanes, while `completed` also grew. kernel-room-nudge.sh got
  # this gate at 23:20; the digest path had only lane_wedged(). ONE predicate now,
  # in scripts/lane-live-check.py, so the two whip paths cannot drift.
  # A BROKEN predicate (rc=2 -> empty) falls through to mentioning: fail OPEN, because
  # an empty list here would be indistinguishable from "everyone is busy" and silence
  # the whip — the failure mode that starved four lanes on 2026-09-20 20:37.
  LIVE_ROWS=$(timeout 6 python3 /home/host/opikernel/scripts/lane-live-check.py "$ROOM" \
    --names-only 2>/dev/null || true)
  lane_live() { [ -n "$LIVE_ROWS" ] && printf '%s\n' "$LIVE_ROWS" | grep -Fxq -- "$1"; }
  if [ -n "$LIVE_ROWS" ]; then
    echo "  [$ROOM] live lanes (mention suppressed while the row is undrained): $(printf '%s' "$LIVE_ROWS" | tr '\n' ' ')"
  fi

  # nudge stale agents (max 4/room/tick, per-role cooldown, global yolo cap)
  CAN_NUDGE=1
  # Count live YOLO agent sessions by their real cmdline, not by the launcher:
  # /home/host/.hermes/bin/yolo execs into `hermes chat --query-file /tmp/yolo-query.*`
  # within ~1s, so pgrep'ing for 'hermes/bin/yolo' always returned 0 and the cap
  # never engaged (checked 2026-09-18). Over-counting here is the safe direction.
  YOLO_RUNNING=$(pgrep -af 'bin/hermes chat' 2>/dev/null | grep -c 'yolo-query' || true)
  YOLO_RUNNING=$(printf '%s' "${YOLO_RUNNING:-0}" | tr -dc '0-9'); [ -z "$YOLO_RUNNING" ] && YOLO_RUNNING=0
  # Placeholder / non-agent roles must never be nudged: 'default' is a UI artifact
  # with no role definition, so a nudge spawns a session that burns budget and
  # reports nothing.
  NUDGE_DENY="${NUDGE_DENY:-default:none:n/a:minecraft:}"
  if [ "$YOLO_RUNNING" -ge "$MAX_YOLO" ]; then
    echo "  [$ROOM] $YOLO_RUNNING yolo session(s) already running (cap $MAX_YOLO); nudges paused this tick"
    CAN_NUDGE=0
  fi
  if [ -n "$STALE" ] && [ "$CAN_NUDGE" = "1" ] && ! digest_will_post "$ROOM" "$ROOM|${STALE_FLAT}|${BLOCK_FLAT}"; then
    i=0
    NUDGED=""
    RETRY_NUDGED=""
    while IFS= read -r role; do
      [ -z "$role" ] && continue
      [ $i -ge 4 ] && break
      if lane_wedged "$role"; then
        echo "  [$ROOM] skip ${role} (lane WEDGED - drain key stuck, mention would be undelivered)"
        continue
      fi
      case ":$NUDGE_DENY:" in *":$role:"*)
        echo "  [$ROOM] skip ${role} (placeholder/non-agent role in NUDGE_DENY)"
        continue ;;
      esac
      if ! nudge_allowed "$ROOM" "$role"; then
        # Cooldown expired?  No — only re-dispatch early when the agent's own last
        # output was a provider/billing failure (it never ran; routing will retry).
        if provider_error "$ROOM" "$role"; then
          RETRY_NUDGED="${RETRY_NUDGED}${RETRY_NUDGED:+
}${role}"
          echo "  [$ROOM] retry ${role} (provider failure — cooldown bypassed, retrying this tick)"
        else
          echo "  [$ROOM] skip ${role} (nudged <${NUDGE_COOLDOWN_MIN}m ago)"
          continue
        fi
      fi
      NUDGED="${NUDGED}${NUDGED:+
}${role}"
      i=$((i+1))
    done <<< "$STALE"
  elif [ -n "$STALE" ] && [ "$CAN_NUDGE" = "1" ]; then
    echo "  [$ROOM] nudge batch skipped — digest is due this tick and will @mention ALL stale workers"
  fi

  # --- nudge delivery: STRUCTURED ROOM MENTION (canon 2026-09-18) --------------
  # Why this is not a local `yolo` spawn any more:
  #   * a room @mention is the ONLY path that runs the agent's real room session
  #     (server: message -> gc_execution_queue row -> agent run). Proved by
  #     gc-post --mention kernel-architect -> queue row status=running.
  #   * plainly typing "@role" does nothing: gc-post used to send
  #     {roomId,content,id} with NO `mentions` key, and the server only routes
  #     from the structured array — so the digest named idle agents but
  #     dispatched nobody (all orchestrator rows: mentions='[]').
  #   * the old local spawn posted as the-human anyway, with no room context.
  # Local spawn is kept ONLY as a fallback if the mention post is rejected.
  if [ -n "${NUDGED:-}" ] && [ -n "$STALE" ]; then
    if ! batch_allowed "$ROOM" && [ -z "${RETRY_NUDGED:-}" ]; then
      echo "  [$ROOM] nudge batch cooling down (<${NUDGE_BATCH_MIN}m) — not posting"
    else
      if [ -n "${RETRY_NUDGED:-}" ]; then
        echo "  [$ROOM] batch cooldown bypassed for provider-failure retry: $(printf '%s' "$RETRY_NUDGED" | tr '\n' ' ')"
      fi
      MARGS=()
      MTOKENS=""
      while IFS= read -r role; do
        [ -z "$role" ] && continue
        MARGS+=(--mention "$role")
        MTOKENS="${MTOKENS}@${role} "
      done <<< "$NUDGED"
      NCONTENT="[orchestrator $(date +%H:%M) auto-nudge room=$ROOM — the orchestrator is speaking, NOT Nick]
${MTOKENS}
idle >${IDLE_MIN}m. Take ONE concrete next step for your role: read your last message and /home/host/opikernel/agentic-pool/<your role>.md, do the work, then reply with <=5 lines of hard evidence (command + result) or a one-line blocker. No todo in your role file? Claim the top 'status: open' item in /home/host/opikernel/agentic-pool/BACKLOG.md (edit it to 'status: claimed' + 'claimed-by: <your role>' BEFORE starting). Board power + serial are LEASED by TelegramRunner (smartplug REFUSED rc=9 is correct); never open the serial port."
      if timeout 25 /usr/local/bin/gc-post --room "$ROOM" --as "orchestrator" --quiet "${MARGS[@]}" "$NCONTENT" >> "$LOG" 2>&1; then
        while IFS= read -r role; do
          [ -z "$role" ] && continue
          mark_nudged "$ROOM" "$role"
          echo "  [$ROOM] nudged via @mention: $role"
        done <<< "$NUDGED"
      else
        echo "  [$ROOM] MENTION POST FAILED — falling back to local yolo spawn" >> "$LOG"
        while IFS= read -r role; do
          [ -z "$role" ] && continue
          ROLE="$role" setsid /home/host/.hermes/bin/yolo "YOLO nudge: room=$ROOM role=$role idle>15min. Do ONE concrete next step for $ROOM. Read your role's last message, then write ONLY to /home/host/opikernel/agentic-pool/$role.md (that exact path; create no other file). Post progress with: gc-post --room $ROOM --as $role. NO @all spam, no asking Nick. Max 3 tool calls, max 4000 words." </dev/null >/dev/null 2>&1 8>&- &
          mark_nudged "$ROOM" "$role"
          echo "  [$ROOM] nudged (fallback spawn): $role"
        done <<< "$NUDGED"
        sleep 1
      fi
    fi
  fi

  # blockers -> append to _blocker-log.txt per room
  # Dedupe (2026-09-20): the blocker set is stable for hours, so this logged the same
  # line every tick — 34 lines for gpu-driver-expert + 33 for 'py specialist' and the
  # latter name never resolves to a participant, so nothing was ever delivered.
  # Same target set per room now logs at most once per BLOCK_LOG_REPEAT_MIN (default 10).
  if [ -n "$BLOCK" ]; then
    BSTATE="$POOL_DIR/.blocker-log.${ROOM}.state"
    BTGT=$(printf '%s' "$BLOCK_FLAT" | md5sum | cut -c1-8)
    NOW=$(date +%s); REPEAT_MIN="${BLOCK_LOG_REPEAT_MIN:-10}"
    LAST_HASH=""; LAST_TS=0; LAST_N=1
    [ -f "$BSTATE" ] && read -r LAST_HASH LAST_TS LAST_N < "$BSTATE" 2>/dev/null
    if [ "$BTGT" = "$LAST_HASH" ]; then
      LAST_N=$(( ${LAST_N:-1} + 1 ))
      if [ $(( (NOW - ${LAST_TS:-0}) / 60 )) -lt "$REPEAT_MIN" ]; then
        echo "  blocker-msg: SUPPRESSED set=$BTGT repeat=#$LAST_N last=$(date -d @${LAST_TS:-0} +%H:%M) (<${REPEAT_MIN}m)"
        printf '%s %s %s\n' "$BTGT" "${LAST_TS:-$NOW}" "$LAST_N" > "$BSTATE"
      else
        MSG="[BLOCKER-$(date +%H:%M) room=$ROOM repeat=#$LAST_N] ${BLOCK} — surface what you're blocked on or mark it done."
        echo "  blocker-msg: $MSG"
        echo "$MSG" >> "$POOL_DIR/_blocker-log.txt"
        printf '%s %s %s\n' "$BTGT" "$NOW" "$LAST_N" > "$BSTATE"
      fi
    else
      MSG="[BLOCKER-$(date +%H:%M) room=$ROOM] ${BLOCK} — surface what you're blocked on or mark it done."
      echo "  blocker-msg: $MSG"
      echo "$MSG" >> "$POOL_DIR/_blocker-log.txt"
      printf '%s %s 1\n' "$BTGT" "$NOW" > "$BSTATE"
    fi
  fi

  # room post (max 1/room/tick) — DIRECT bash post via gc-post (no agent session,
  # no inference, no gc_post_message dependency). Verified working 2026-09-18.
  # Dedupe + cooldown added 2026-09-18: the detector's verdict is stable for long
  # stretches (same stale set every minute), and posting it every tick is 1,440
  # messages/day of pure noise. Post when the set CHANGES, or as a heartbeat at
  # most once per ORCH_POST_COOLDOWN_MIN.
  POST_STATE="${POST_STATE:-/home/host/opikernel/state/orchestrator-post-state.json}"
  # --- mentionable roster (SERVER TRUTH) ---------------------------------------
  # The server validates every structured mention against
  #   getRoomAgents(room) = SELECT ... FROM gc_room_agents WHERE roomId=? AND removedAt=0
  # and REJECTS THE WHOLE MESSAGE if one entry fails ("Invalid structured mentions"
  # -> ack.error). Live proof: 'default' is removedAt=1788723810203, so a naive
  # "mention every stale name" build kills the digest post outright and the room
  # goes silent — which is exactly what looked like "the nagger isn't doing it".
  ROSTER=$(sqlite3 "$DB_GC" "SELECT name FROM gc_room_agents WHERE roomId='$ROOM' AND removedAt=0;" 2>/dev/null | sort)
  roster_has() { printf '%s\n' "$ROSTER" | grep -Fxq -- "$1"; }
  if [ -n "$STALE" ] || [ -n "$BLOCK" ]; then
    # PA 2026-09-20: this used to be `ls *.md | wc -l` -- a FILE count of evidence dumps that
    # grows monotonically and measures no throughput, which is how a frozen queue (13 claimed /
    # 0 open / 0 closed in 24 h) kept telling the room "pool=129 files". Report the ledger.
    # PA 2026-09-20 21:45: bucket `blocked` was MISSING from this counter, so the digest read
    # `claimed=14/open=0/done=6` against a 24-item ledger while 4 blocker rows sat invisible --
    # i.e. `blockers=none` was arithmetically impossible, not a fact, and it hid a 3h21m dark
    # board (capture frozen 18:17:07, ping FAIL). Count every terminal state AND self-check the
    # sum against the `### BL-NN` heading count so a dropped bucket can never recur silently.
    cnt=$(awk '/^status: claimed/{c++} /^status: open/{o++} /^status: done/{d++} /^status: blocked/{b++}
               /^### BL-/{h++}
               END{printf "claimed=%d/open=%d/done=%d/blocked=%d/total=%d", c+0, o+0, d+0, b+0, c+o+d+b;
                   if ((c+o+d+b)!=h) printf " MISMATCH(headings=%d)", h+0}' "$POOL_DIR/BACKLOG.md" 2>/dev/null)
    [ -z "$cnt" ] && cnt="claimed=?/open=?/done=?/blocked=? (BACKLOG.md unreadable)"
    KEY="$ROOM|${STALE_FLAT}|${BLOCK_FLAT}"
    if python3 - "$POST_STATE" "$KEY" "${ORCH_POST_COOLDOWN_MIN:-15}" <<'PYK' 2>/dev/null
import hashlib, json, os, sys, time
p, key, cool = sys.argv[1], sys.argv[2], int(sys.argv[3]) * 60
k = hashlib.sha1(key.encode()).hexdigest()[:16]
try:
    d = json.load(open(p))
except Exception:
    d = {}
last = d.get(key.split("|", 1)[0], {})
if last.get("hash") == k and (time.time() - last.get("ts", 0)) < cool:
    print("unchanged")
    sys.exit(1)
d[key.split("|", 1)[0]] = {"hash": k, "ts": time.time()}
tmp = p + ".tmp"
json.dump(d, open(tmp, "w"))
os.replace(tmp, p)
PYK
    then
      # --- build the mention set from the SAME names that appear in the text ------
      # Invariant the server enforces (content token per mention) : every
      # structured mention MUST also appear as a literal '@name' in the content,
      # so the two are generated together and can never drift.
      MARGS=(); MTOKENS=""; MENTIONED=""; MCOUNT=0; MDENIED=0
      while IFS= read -r role; do
        [ -z "$role" ] && continue
        [ "$MCOUNT" -ge "${MAX_MENTIONS:-10}" ] && break
        case ":${MENTION_DENY:-$NUDGE_DENY}:" in *":$role:"*)
          # 'default' is a UI placeholder (and is removedAt>0 in gc_room_agents).
          # Keep it out of the text entirely — "default(denied)" every tick is the
          # kind of noise that makes a real digest unreadable.
          MDENIED=$((MDENIED+1))
          continue ;;
        esac
        if lane_wedged "$role"; then
          # text only - never a structured mention into a stuck drain key
          MTOKENS="${MTOKENS}${role}~(wedged) "
          echo "  [$ROOM] digest: '$role' lane WEDGED - listed as text only, no mention"
          continue
        fi
        if lane_live "$role"; then
          # text only - the lane already owns an undrained running|queued row. A new
          # structured mention only mints another row for a lane that is demonstrably
          # busy (see the live-row gate above), which is how one lane collected 5 rows
          # in 6 min. `completed` still climbs; nothing is starved by staying quiet.
          MTOKENS="${MTOKENS}${role}~(running) "
          echo "  [$ROOM] digest: '$role' already has an undrained row - listed as text only, no mention"
          continue
        fi
        if roster_has "$role"; then
          MARGS+=(--mention "$role")
          MTOKENS="${MTOKENS}@${role} "
          MENTIONED="${MENTIONED}${MENTIONED:+
}${role}"
          MCOUNT=$((MCOUNT+1))
        else
          # not in gc_room_agents(removedAt=0) -> unmentionable; keep the name visible
          # but NEVER put it in the structured array (that kills the whole post).
          MTOKENS="${MTOKENS}${role} "
          echo "  [$ROOM] digest: '${role}' not mentionable (not a live room agent) — listed as text only"
        fi
      done <<< "$STALE"
      [ "${MDENIED:-0}" -gt 0 ] && MDNOTE="(${MDENIED} unmentionable) " || MDNOTE=""
      # --- derived blockers (2026-09-20, PA) -----------------------------------
      # `blockers=${BLOCK:-none}` printed "none" in 13/13 digests while the named
      # agents' own mentions were being reaped undelivered (0 completed rows, all
      # rows status=queued + startedAt NULL). The field was an empty placeholder,
      # so the room whipped agents whose mentions never arrived and could not tell
      # that apart from "working". Derive it from gc_execution_queue for the SAME
      # names in the text; fall back to the old value so nothing regresses.
      BLOCK_DERIVED="none"
      if [ -n "${MENTIONED:-}" ] && [ -x /home/host/opikernel/scripts/pa-queue-blocker-field.py ]; then
        mapfile -t QNAMES <<< "$MENTIONED"
        BLOCK_DERIVED=$(timeout 6 python3 /home/host/opikernel/scripts/pa-queue-blocker-field.py "$ROOM" "${QNAMES[@]}" 2>/dev/null)
        [ -z "$BLOCK_DERIVED" ] && BLOCK_DERIVED="none"
      fi
      if [ "$BLOCK_DERIVED" != "none" ]; then
        case "${BLOCK:-none}" in
          none|"") BLOCK_FIELD="$BLOCK_DERIVED" ;;
          *)       BLOCK_FIELD="${BLOCK};${BLOCK_DERIVED}" ;;
        esac
      else
        BLOCK_FIELD="${BLOCK:-none}"
      fi
      STATUS="[orchestrator $(date +%H:%M) room=$ROOM] stale=${MTOKENS:-none}${MDNOTE}blockers=${BLOCK_FIELD} pool[${cnt}]."
      unset MDNOTE
      POSTED=0
      if [ -x /usr/local/bin/gc-post ]; then
        if [ ${#MARGS[@]} -gt 0 ]; then
          if timeout 25 /usr/local/bin/gc-post --room "$ROOM" --as "orchestrator" --quiet "${MARGS[@]}" "$STATUS" >> "$LOG" 2>&1; then
            echo "  [$ROOM] posted (direct, ${MCOUNT} mention(s)): $STATUS"
            POSTED=1
          else
            echo "  [$ROOM] MENTION POST REJECTED — retrying text-only so the status still lands" >> "$LOG"
          fi
        fi
        # Text-only fallback: a rejected mention must never cost us the digest.
        if [ "$POSTED" -eq 0 ]; then
          if timeout 25 /usr/local/bin/gc-post --room "$ROOM" --as "orchestrator" --quiet "$STATUS" >> "$LOG" 2>&1; then
            echo "  [$ROOM] posted (direct, text-only): $STATUS"
            POSTED=1
          else
            echo "$STATUS" >> "$POOL_DIR/_room-post-failed.log"
            echo "  [$ROOM] DIRECT POST FAILED, queued: $STATUS"
          fi
        fi
        # The digest just dispatched these agents (1 mention = 1 gc_execution_queue
        # row = 1 agent run, verified). Mark them nudged so the per-role nudge batch
        # below does not double-dispatch them in the same window.
        if [ "$POSTED" -eq 1 ] && [ -n "$MENTIONED" ]; then
          while IFS= read -r role; do
            [ -z "$role" ] && continue
            mark_nudged "$ROOM" "$role"
          done <<< "$MENTIONED"
        fi
      else
        echo "  [$ROOM] gc-post not installed; queued: $STATUS" >> "$POOL_DIR/_room-post-failed.log"
      fi
    else
      echo "  [$ROOM] digest unchanged (<${ORCH_POST_COOLDOWN_MIN:-15}m) — not posting"
    fi
  fi

  # heartbeat per room
  echo "$(date +%s) orchestrator-tick room=$ROOM stale=$STALE blockers=$BLOCK" >> /home/host/opikernel/logs/orchestrator-heartbeat.log
done
  # Self-scheduling loop (restored 2026-09-19). The provider-retry backup
  # this was built from is a CRON one-shot: it ran ONE tick then exited, so
  # nothing re-triggered after the first minute. Every agent read as
  # permanently stale, the @all nudge never fired, and the watchdog was
  # disabled on top — the whole churn guard was dead while Nick was asking
  # why nobody was working. Wrapping the body in a 60s loop fixes it.
  # also drop a group-level heartbeat
  echo "$(date +%s) orchestrator-tick-group rooms=${ROOMS:-none}" >> /home/host/opikernel/logs/orchestrator-heartbeat.log 2>/dev/null

  sleep "${TICK_SLEEP:-60}"
done
exit 0
