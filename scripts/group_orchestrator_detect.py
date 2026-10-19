#!/usr/bin/env python3
"""Detect idle agents in hermes group-chat rooms (multi-room).
Reads env: DB_GC=/home/host/.hermes-web-ui/hermes-web-ui.db
Writes /home/host/opikernel/state/orchestrator.json with per-room stale/active/blockers.

New in group mode: loops ALL rooms in gc_rooms, not just one ROOM_ID.
Auto-clears is handled by the shell wrapper, not here.
"""
import os, sqlite3, json, time, sys

db_gc = os.environ.get("DB_GC", "/home/host/.hermes-web-ui/hermes-web-ui.db")
idle_min = int(os.environ.get("IDLE_MIN", "7"))
block_age_min = int(os.environ.get("BLOCK_AGE_MIN", "6"))
now_ms = int(time.time() * 1000)
now_s = time.time()

blocker_keys = ("waiting on", "blocked by", "needs review", "stuck",
                "unclear", "depends on", "blocker:")

try:
    con = sqlite3.connect(db_gc)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
except Exception as e:
    print(f"DB open failed: {e}", file=sys.stderr)
    sys.exit(1)

# discover rooms
try:
    rooms = [r[0] for r in cur.execute("SELECT id FROM gc_rooms").fetchall()]
except Exception as e:
    print(f"rooms query failed: {e}", file=sys.stderr)
    sys.exit(1)

# --- room targeting (2026-09-18) -------------------------------------------
# BUG THIS FIXES: this detector looped ALL rooms in gc_rooms, so the every-minute
# poller nudged a DORMANT room (Neorunner, last agent traffic 16h+, human never
# posts) whose 6 agents are permanently "stale". Result: 8,748 nudges, a fresh
# YOLO agent session every 60s, and board power-cycle reports posted into that
# dead room instead of the live project room. The room that matters never got a
# nudge. Rooms are now selected by ATTENDANCE:
#   * ORCH_ROOMS (space/comma list) -> authoritative allowlist when set
#   * ORCH_ROOMS_EXCLUDE            -> explicit kill list
#   * otherwise: a room is processed only if a NON-AGENT participant (a human)
#     has posted in it within ROOM_HUMAN_MIN minutes. Agents nudge themselves
#     into a loop; a room with no human is a room nobody is waiting on.
attended_min = int(os.environ.get("ROOM_HUMAN_MIN", "2880"))   # 48h
allow = (os.environ.get("ORCH_ROOMS", "") or "").replace(",", " ").split()
deny = set((os.environ.get("ORCH_ROOMS_EXCLUDE", "") or "").replace(",", " ").split())
skipped = {}
selected = []
for room in rooms:
    if allow and room not in allow:
        skipped[room] = "not-in-ORCH_ROOMS"
        continue
    if room in deny:
        skipped[room] = "excluded"
        continue
    agent_names = {r[0] for r in cur.execute(
        "SELECT name FROM gc_room_agents WHERE roomId=?", (room,)).fetchall()}
    # --- attendance must not depend on a message WINDOW (2026-09-18 15:35) -----
    # BUG THIS FIXES: attendance was scored by scanning the newest 200 rows and
    # taking the first sender that is not a room agent. The bridge mirror flood
    # (raw tool results posted as each agent's own name) pushes a real human post
    # past row 200 within minutes, so the LIVE room read as
    # "unattended (no human post in 1666.7h)" — last_human=0, the 99999-minute
    # fallback — and the orchestrator skipped the whole room: zero nudges, again.
    # Ask the DB directly for the newest non-agent message instead of windowing.
    # --- attendance must key off senderType, never a sender NAME (2026-09-18 PA) --
    # BUG THIS FIXES: the non-agent set was built as
    #   sorted(set(agent_names) | {"admin", "orchestrator"})
    # and used as a NOT-IN blacklist. The Neorunner room's ONLY human member is
    # literally named `admin` (gc_messages.senderName='admin', senderType=
    # 'member'), so the room's own human posts were excluded by name and the room
    # read "unattended (no human post in 1666.7h)" (last_human=0, the 99999-min
    # fallback) on every tick — zero nudges dispatched into a live room with a
    # human sitting in it. KernelDev-GPU was unaffected only because its human is
    # named `the-human`. Classify by senderType instead: agent/bot senders are
    # machine output (the bridge mirrors raw tool results as each agent's own
    # name), everything else is a member. The orchestrator's own digests are
    # filtered by their '[orchestrator ' content prefix, not by author name.
    last_human = 0
    try:
        hrows = cur.execute(
            "SELECT senderName, senderType, timestamp FROM gc_messages "
            "WHERE roomId=? AND content NOT LIKE '[orchestrator %' "
            "AND (senderType IS NULL OR senderType NOT IN ('agent','bot')) "
            "ORDER BY timestamp DESC LIMIT 50",
            (room,),
        ).fetchall()
        for r in hrows:
            if r["senderName"] not in agent_names:
                last_human = r["timestamp"] or 0
                break
    except Exception as e:
        print(f"attendance query failed for {room}: {e}", file=sys.stderr)
    if not last_human:
        # Fallback: if the room has no member posts at all, fall back to the
        # newest non-agent-authorship message regardless of senderType.
        row = cur.execute("""
            SELECT senderName, timestamp FROM gc_messages
            WHERE roomId=? AND content NOT LIKE '[orchestrator %'
            ORDER BY timestamp DESC LIMIT 200
        """, (room,)).fetchall()
        for r in row:
            if r["senderName"] not in agent_names:
                last_human = r["timestamp"] or 0
                break
    age_min = (now_ms - last_human) / 60000.0 if last_human else 99999.0
    if not allow and age_min > attended_min:
        skipped[room] = f"unattended (no human post in {age_min/60:.1f}h)"
        continue
    selected.append(room)

for r, why in skipped.items():
    print(f"SKIP room {r}: {why}", file=sys.stderr)
rooms = selected

if not rooms:
    out = {"rooms": {}, "skipped": skipped, "ts": now_s}
    print(json.dumps(out, indent=2))
    with open("/home/host/opikernel/state/orchestrator.json", "w") as f:
        json.dump(out, f)
    sys.exit(0)

out = {"rooms": {}, "skipped": skipped, "ts": now_s,
       "idle_min": idle_min, "block_age_min": block_age_min}

for room in rooms:
    agents = list(cur.execute("SELECT agentId, name FROM gc_room_agents WHERE roomId=?", (room,)).fetchall())
    if not agents:
        continue
    stale, active, blockers = [], [], []
    stuck_pending = 0
    for agent_id, name in agents:
        # Activity signal #1: the last message THIS agent actually posted.
        # (The old query had no sender filter — it used the newest message in the
        # room for EVERY agent, so blocker keywords were matched against whoever
        # spoke last and agent-specific idleness was invisible.)
        msg_row = cur.execute("""
            SELECT content, timestamp FROM gc_messages
            WHERE roomId=? AND senderName=? ORDER BY timestamp DESC LIMIT 1
        """, (room, name)).fetchone()
        msg_age_min = None
        if msg_row and msg_row["timestamp"]:
            msg_age_min = (now_ms - msg_row["timestamp"]) / 60000.0
        last_msg = ((msg_row["content"] or "")[:200] if msg_row else "")

        # Activity signal #2: last EXECUTED queue row. status='pending' is excluded
        # on purpose: step 3a of group-orchestrator.sh bumps createdAt on unstarted
        # pending rows every 60s, so a pending row's age is always ~0. Keying
        # staleness off it made every agent look active forever and silenced the
        # nagger completely (stale=[] every tick, 0 nudges since the room fix).
        row = cur.execute("""
            SELECT status, createdAt, finishedAt, lastError
            FROM gc_execution_queue
            WHERE roomId=? AND targetAgentId=? AND status <> 'pending'
            ORDER BY createdAt DESC LIMIT 1
        """, (room, agent_id)).fetchone()

        if row is None:
            q_age = 9999.0
        else:
            last_ts = row["finishedAt"] if row["finishedAt"] else row["createdAt"]
            q_age = (now_ms - last_ts) / 60000.0 if last_ts else 9999.0

        # Stuck-queue telemetry: pending for real (never started) is counted, not
        # scored as activity.
        sp = cur.execute("""
            SELECT COUNT(*) FROM gc_execution_queue
            WHERE roomId=? AND targetAgentId=? AND status='pending' AND startedAt IS NULL
        """, (room, agent_id)).fetchone()[0]
        stuck_pending += sp or 0

        # A message is the real proof an agent is working; queue rows only fill in
        # for agents that have never spoken in the room.
        age_min = msg_age_min if msg_age_min is not None else q_age
        last_err = row["lastError"] if row else None
        status = row["status"] if row else "never-ran"

        low = (last_msg or last_err or "").lower()
        if age_min > idle_min:
            if any(k in low for k in blocker_keys):
                blockers.append([name, round(age_min, 1), last_msg or last_err])
            else:
                stale.append([name, round(age_min, 1), last_msg or last_err or status])
        else:
            active.append([name, round(age_min, 1), last_msg[:80] if last_msg else status])

    # also check if handoff chain is stuck (depth == maxDepth and stopped)
    stuck_chain = cur.execute("""
        SELECT chainId, currentDepth, maxDepth, stopReason, status
        FROM gc_handoff_chains
        WHERE roomId=? AND status='stopped' AND stopReason='max_depth'
        ORDER BY createdAt DESC LIMIT 1
    """, (room,)).fetchone()
    chain_info = dict(stuck_chain) if stuck_chain else None

    out["rooms"][room] = {
        "stale": stale,
        "active": active,
        "blockers": blockers,
        "stuck_pending": stuck_pending,
        "chain_stuck": chain_info,
        "agent_count": len(agents)
    }

with open("/home/host/opikernel/state/orchestrator.json", "w") as f:
    json.dump(out, f, default=str)

print(json.dumps(out, indent=2))
