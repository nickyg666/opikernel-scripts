#!/bin/bash
# /home/host/opikernel/scripts/startup-kick.sh
# Re-queues stale pending broadcasts and nudges workers after a webui/gateway restart.
# Installed as: hermes cron on_boot job (fires once per boot) + plain file fallback.
set -e
python3 << 'PY'
import sqlite3, json, time, uuid
DB = "/home/host/.hermes-web-ui/hermes-web-ui.db"
import sqlite3 as sql
con = sql.connect(DB)
ROOM = "mti5ax1clq0zlx"
# Ghost rows in gc_room_agents (no live session, never dispatchable) — queueing them
# creates 'pending' rows with startedAt NULL that never change status and poison the
# stale/nudge calculation. Observed 2026-09-19: rows from gcmsg_startup_1789734807023
# sat pending 25.6h for 'default' / 'project analyzer'.
GHOSTS = {"default", "project analyzer"}
# 1) nuke anything stuck in 'pending'/'queued' that was never picked up by a worker
#    (startedAt IS NULL) and is older than 10 min -> undeliverable, keeps stale list hot
now = int(time.time()*1000)
cutoff = now - 60_000
undeliv = now - 600_000
rows = list(con.execute("SELECT DISTINCT messageId FROM gc_execution_queue WHERE status='pending' AND createdAt < ? AND roomId=?", (cutoff, ROOM)))
for (mid,) in rows:
    con.execute("DELETE FROM gc_execution_queue WHERE messageId=?", (mid,))
    print(f"startup-kick: removed stale {mid[:20]}")
n = con.execute("DELETE FROM gc_execution_queue WHERE roomId=? AND status IN ('pending','queued') AND startedAt IS NULL AND createdAt < ?", (ROOM, undeliv)).rowcount
print(f"startup-kick: purged {n} never-started queue rows (>10min, startedAt NULL)")
# 2) insert fresh broadcast — mentions MUST carry participantIds or the web-ui
#    dispatcher creates rows that are never delivered (mentions='[]' is a dead row).
agents = [(a, n_) for (a, n_) in con.execute("SELECT agentId, name FROM gc_room_agents WHERE roomId=?", (ROOM,)) if n_ not in GHOSTS]
if not agents:
    print("startup-kick: no agents found, skip")
    con.commit()
    exit(0)
# dedupe with the 60s cutoff above — we already cleared, so insert
max_seq = con.execute("SELECT COALESCE(MAX(sequence), 0) FROM gc_execution_queue").fetchone()[0]
msg_id = f"gcmsg_startup_{now}"
body = "@all UNBLOCK — work together, unify docs + kanban. Don't stop till done. Brother, keep moving. There is no blocker."
now2 = int(time.time()*1000)
mentions = json.dumps([{"type": "agent", "participantId": a} for (a, _) in agents])
con.execute("INSERT INTO gc_messages (id, roomId, senderId, senderName, senderType, content, timestamp, persistedAt, mentions, role, finish_reason) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
    (msg_id, ROOM, "auth:1", "nickyg666", "user", body, now2, now2, mentions, "user", None))
h = "ca12f087413775e9ab3218a20236927e62c3b37f7f47f895173722dc81114b64"
for i, (agentId, agentName) in enumerate(agents):
    qid = str(uuid.uuid4())
    seq = max_seq + 1 + i
    con.execute("INSERT INTO gc_execution_queue (id, roomId, messageId, targetAgentId, targetAgentName, requesterMemberId, cancelCapabilityHash, textSummary, sequence, status, createdAt) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (qid, "mti5ax1clq0zlx", msg_id, agentId, agentName, "auth:1", h, body, seq, "pending", now2))
    print(f"queued seq={seq} agent={agentName}")
con.execute("DELETE FROM gc_handoff_chains WHERE roomId='mti5ax1clq0zlx'")
con.commit()
print("startup-kick: done")
PY
