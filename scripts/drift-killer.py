#!/usr/bin/env python3
# RETIRED 2026-09-18 — cron entry removed; superseded by agent-drift-guard.py.
# Why: this file's stop path (`pgrep -af "hermes chat"` then SIGTERM) matches no
# process for a group-chat agent. gc agent turns run INSIDE the shared
# hermes_bridge.py worker (pid with --worker-profile default), never as a
# `hermes chat` child — so the kill was a no-op and the agent kept drifting.
# agent-drift-guard.py also detects repeat-within-one-message (a real observed
# failure this detector misses) and stops turns via the bridge `interrupt` action
# (proven: "Turn ended: reason=interrupted_during_api_call").
# Kept for reference — its live-drift gate (newest message must BE the repeat)
# was adopted into the guard. Do not re-add its cron entry.
"""drift-killer.py — stop agents that are looping on identical output, restart them.

the-human 2026-09-18: "if you see an agent output the same exact output 3x, stop it
and start it again so it does not run off into driftland."

Detection (deterministic, zero inference):
  For each sender in a groomed room, look at that sender's own last N messages
  (gc_messages, whitespace-normalised content, >= 20 chars). If the SAME text
  covers >= RUN_LEN of that sender's most recent messages, it is a drift loop.
  Interleaved messages from other senders do not break the run — the loop is a
  property of that agent's own output stream.

Action ("stop it and start it again"):
  1. SIGTERM -> SIGKILL the live `hermes chat` process bound to that agent's
     newest open gc_ session (matched by session id inside the cmdline).
  2. Mark that session ended in /home/host/.hermes/state.db with
     end_reason='drift-loop-killed' so agent-watchdog.sh cannot resume it
     (watchdog only resumes s.ended_at IS NULL).
  3. Delete the agent's nudge-state key so group-orchestrator.sh re-dispatches a
     FRESH session on the very next tick (restart, not wait-for-cooldown).

DRY_RUN=1  -> detect and print only, touch nothing.
Never touches the board, serial, or power. Safe to run every minute.
"""
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import time

try:
    import fcntl
except ImportError:      # pragma: no cover — non-POSIX
    fcntl = None

DB_GC = os.environ.get("DB_GC", "/home/host/.hermes-web-ui/hermes-web-ui.db")
DB_STATE = os.environ.get("DB", "/home/host/.hermes/state.db")
NUDGE_STATE = os.environ.get("NUDGE_STATE", "/home/host/opikernel/state/nudge-state.json")
LOG = os.environ.get("DRIFT_LOG", "/home/host/opikernel/logs/drift-killer.log")
ROOMS = [r for r in (os.environ.get("ORCH_ROOMS", "mti5ax1clq0zlx") or "").replace(",", " ").split() if r]
LOOKBACK = int(os.environ.get("DRIFT_LOOKBACK", "8"))    # messages per sender to inspect
RUN_LEN = int(os.environ.get("DRIFT_RUN_LEN", "3"))      # identical in a row == drift
MIN_LEN = int(os.environ.get("DRIFT_MIN_LEN", "20"))     # ignore trivial/empty posts
DRY = os.environ.get("DRY_RUN", "") not in ("", "0", "false")
SELF_NAMES = {"orchestrator", "system", "the-human"}


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def norm(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def sid_fragment(agent):
    return re.sub(r"[^A-Za-z0-9]+", "_", agent)


def find_loops(con, room):
    """-> [(agent, count, sample)] for every sender currently repeating itself.

    Rule: the sender's NEWEST message must be a text that also appears >= RUN_LEN
    times inside its own last LOOKBACK messages. Repeats need not be strictly
    adjacent (agents interleave their own posts with tool output), but the loop
    must be live right now — a burst that stopped is not a drift.
    """
    rows = con.execute(
        "SELECT senderName, content FROM gc_messages "
        "WHERE roomId=? AND senderType!='user' ORDER BY timestamp DESC LIMIT 400",
        (room,),
    ).fetchall()
    per_sender = {}
    for name, content in rows:                     # newest-first
        if name in SELF_NAMES:
            continue
        texts = per_sender.setdefault(name, [])
        if len(texts) < LOOKBACK:
            texts.append(norm(content))
    hits = []
    for agent, texts in per_sender.items():
        if not texts:
            continue
        newest = texts[0]
        if len(newest) < MIN_LEN or newest.startswith('{"kind":"workspace_diff"'):
            continue
        count = sum(1 for t in texts if t == newest)
        if count >= RUN_LEN:
            hits.append((agent, count, newest[:120]))
    return hits


def open_session(con, agent):
    frag = sid_fragment(agent)
    row = con.execute(
        "SELECT id FROM sessions WHERE id LIKE 'gc_%' AND id LIKE ? AND ended_at IS NULL "
        "ORDER BY started_at DESC LIMIT 1",
        (f"%{frag}%",),
    ).fetchone()
    return row[0] if row else None


def kill_process(sid):
    killed = []
    if not sid:
        return killed
    try:
        out = subprocess.run(["pgrep", "-af", "hermes chat"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return killed
    for line in out.splitlines():
        if sid not in line:
            continue
        # Self-match guards: a wrapper shell that merely *quotes* the session id in
        # its command line (pgrep patterns, hermes snapshot wrappers) is not the
        # session process — killing it would SIGTERM the caller's own shell.
        if "pgrep" in line or "hermes-snap-" in line or "drift-killer" in line:
            continue
        pid = int(line.split(None, 1)[0])
        if pid == os.getpid():
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except ProcessLookupError:
            pass
    if killed:
        time.sleep(3)
        for pid in killed:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    return killed


def clear_nudge(room, agent):
    try:
        with open(NUDGE_STATE) as fh:
            d = json.load(fh)
    except Exception:
        return False
    key = f"{room}|{agent}"
    if key in d:
        del d[key]
        tmp = NUDGE_STATE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(d, fh)
        os.replace(tmp, NUDGE_STATE)
        return True
    return False


def self_test():
    """Both-directions check of the detector. `python3 drift-killer.py --self-test`."""
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE gc_messages (roomId TEXT, senderName TEXT, senderType TEXT, content TEXT, timestamp INTEGER)")
    room = "testroom"
    rows = []
    t = 1000
    # A: live loop — identical newest text x3, non-adjacent in its own stream
    for content in ["LOOPED PAYLOAD alpha beta gamma", "other work", "LOOPED PAYLOAD alpha beta gamma", "more", "LOOPED PAYLOAD alpha beta gamma"]:
        t += 1
        rows.append((room, "looper", "agent", content, t))
    # B: burst that already stopped (newest differs) — must NOT fire
    for content in ["STOPPED PAYLOAD one two three", "STOPPED PAYLOAD one two three", "STOPPED PAYLOAD one two three", "brand new result"]:
        t += 1
        rows.append((room, "recovered", "agent", content, t))
    # C: bridge workspace_diff mirrors — must NOT fire
    for _ in range(3):
        t += 1
        rows.append((room, "mirror", "agent", '{"kind":"workspace_diff","version":1,"room_id":"x"}', t))
    # D: healthy agent, all unique
    for i in range(4):
        t += 1
        rows.append((room, "worker", "agent", f"unique result number {i} with detail", t))
    con.executemany("INSERT INTO gc_messages VALUES (?,?,?,?,?)", rows)
    got = {a for a, _, _ in find_loops(con, room)}
    ok = got == {"looper"}
    print(f"self-test: detected={sorted(got)} expected=['looper'] -> {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main():
    if "--self-test" in sys.argv:
        return self_test()
    if not ROOMS:
        return 0
    # Never stack runs: two ticks both read "drift" and both kill/restart the
    # same agent. Non-blocking lock; a contended tick exits 0 quietly.
    lock_path = os.environ.get("DRIFT_LOCK", "/home/host/opikernel/state/drift-killer.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    lock_fh = open(lock_path, "w")
    if fcntl is not None:
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            log("another drift-killer instance is running; tick skipped")
            return 0
    gc = sqlite3.connect(DB_GC)
    st = sqlite3.connect(DB_STATE)
    actions = 0
    for room in ROOMS:
        for agent, run, sample in find_loops(gc, room):
            log(f"DRIFT room={room} agent={agent} run={run}x sample={sample!r}")
            if DRY:
                continue
            sid = open_session(st, agent)
            killed = kill_process(sid)
            if sid:
                st.execute(
                    "UPDATE sessions SET ended_at=?, end_reason=? WHERE id=? AND ended_at IS NULL",
                    (time.time(), "drift-loop-killed", sid),
                )
                st.commit()
            cleared = clear_nudge(room, agent)
            st_frag = sid or "no-open-session"
            log(f"KILLED room={room} agent={agent} session={st_frag} pids={killed or 'none'} "
                f"session_closed={bool(sid)} nudge_key_cleared={cleared} -> restart next tick")
            actions += 1
    gc.close()
    st.close()
    if not actions:
        log(f"{'DRY-RUN: ' if DRY else ''}no drift loops detected "
            f"(run>={RUN_LEN}, lookback={LOOKBACK}, rooms={ROOMS})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
