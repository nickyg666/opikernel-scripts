#!/bin/bash
# mti5-nudge.sh — MINIMAL regular nudge for the KernelDev-GPU room, per Nick 2026-09-21:
#   "We just need to nudge agents regularly, they don't need extra context and rules."
#
# Replaces kernel-room-nudge.sh's machinery for mti5: no circuit breaker, no quarantine
# postings, no dead-lane escalation prose, no "do ONE bounded action / <=5 lines" rule text.
# Just: every IDLE_MIN, mention each silent agent with a two-line nudge.
#
# Dedupe still applies (one nudge per agent per NUDGE_INTERVAL) and agents with an
# UNDRAINED dispatch row (queued/running, started) are skipped — mentioning a busy lane
# just piles duplicate rows.
set -uo pipefail

ROOM="${ROOM_ID:-mti5ax1clq0zlx}"
DB_GC="${DB_GC:-/home/host/.hermes-web-ui/hermes-web-ui.db}"
STATE_FILE="${STATE_FILE:-/home/host/opikernel/state/mti5-nudge-state.json}"
NUDGE_INTERVAL="${NUDGE_INTERVAL:-900}"    # >=15 min between nudges of the SAME agent
IDLE_MIN="${IDLE_MIN:-15}"                 # silent longer than this == gets a nudge
GHOSTS="${GHOSTS:-default,project analyzer,minecraft,kconfig-auditor}"

mkdir -p "$(dirname "$STATE_FILE")"
[ -f "$STATE_FILE" ] || echo '{}' > "$STATE_FILE"

python3 - "$ROOM" "$IDLE_MIN" "$GHOSTS" "$STATE_FILE" "$NUDGE_INTERVAL" <<'PY'
import json, sqlite3, subprocess, sys, time

room, idle_min, ghosts_s, state_file, interval = sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4], float(sys.argv[5])
ghosts = {g.strip() for g in ghosts_s.split(",") if g.strip()}
now_ms = time.time() * 1000
now = time.time()

try:
    state = json.load(open(state_file))
except Exception:
    state = {}

con = sqlite3.connect("/home/host/.hermes-web-ui/hermes-web-ui.db")
con.row_factory = sqlite3.Row
agents = con.execute("SELECT agentId, name FROM gc_room_agents WHERE roomId=? AND (removedAt IS NULL OR removedAt=0)",
                     (room,)).fetchall()

for a in agents:
    name = a["name"]
    if name in ghosts:
        continue
    # busy? has an undrained dispatched row -> skip
    q = con.execute("""SELECT status, startedAt FROM gc_execution_queue
                       WHERE roomId=? AND targetAgentId=? AND status IN ('queued','running','pending')
                       ORDER BY createdAt DESC LIMIT 1""", (room, a["agentId"])).fetchone()
    if q and (q["status"] != "queued" or q["startedAt"]):
        print(f"busy: {name}")
        continue
    m = con.execute("""SELECT timestamp FROM gc_messages
                       WHERE roomId=? AND senderName=? ORDER BY timestamp DESC LIMIT 1""",
                    (room, name)).fetchone()
    age = (now_ms - m["timestamp"]) / 60000.0 if (m and m["timestamp"]) else 9999.0
    if age <= idle_min:
        continue
    if now - float(state.get(f"{room}|{name}", 0)) < interval:
        continue
    # Per Nick 2026-09-21 18:51: ask differently — allow multi-step work, order
    # context dumps to files/obsidian, and FORBID verbatim repeats (drift-guard kills them).
    msg = (f"@{name} — nudge: work your task in a multi-step chain (2+ steps), "
           f"do NOT re-post your previous message or error verbatim — repeating text is forbidden. "
           f"If context is full, run /compress or /new; dump findings to Obsidian Session-Logs "
           f"or agentic-pool/notes/ and post one NEW evidence line (command + result).")
    r = subprocess.run(["gc-post", "--room", room, "--as", "TelegramRunner",
                        "--mention", name, msg], capture_output=True, text=True)
    ok = r.returncode == 0
    print(f"{'nudged' if ok else 'POST-FAILED'}: {name} ({age:.0f}m silent)")
    if ok:
        state[f"{room}|{name}"] = str(now)

json.dump(state, open(state_file, "w"))
print("done")
PY
