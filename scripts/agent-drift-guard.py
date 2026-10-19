#!/usr/bin/env python3
"""agent-drift-guard — detect an agent looping on the SAME output and restart it.

Why: an agent whose turn dies mid-stream (provider billing/429, gateway hiccup,
re-dispatched nudge) re-emits its last answer instead of doing new work. Left
alone it burns tokens and floods the room ("driftland"). Observed for real:

  Backlog-worker2 posted a single 11,162-char message at 15:14:04 containing the
  room history echoed back — the line ``kernel-architect：**Step 1: Verify ...**
  `` repeated dozens of times inside ONE message. The same failure also shows up
  as one agent posting the identical block 3+ times, or as an A,B,C,A,B,C,A,B,C
  cycle of its own previous answers.

Detection (three independent signals, all normalized-content based):
  S1 repeat-within-message : one line repeated >= MIN_REPEAT inside one message
  S2 repeat-across-messages: identical message body >= MIN_REPEAT in the window
                             (bridge mirrors + no-op status probes are filtered —
                              see NOOP_RE: firing on "queue is empty" punished the
                              correct answer and the restart re-created the repeat)
  S3 message cycle         : last 3*p messages are 3 identical repetitions of a
                             p-message cycle (p <= 8)

Reaction (--apply):  <-- the "stop it and start it again" part
  1. interrupt the agent's in-flight turn(s) via the agent-bridge unix socket
     ({"action":"interrupt"}) — the supported cooperative stop. Never kill the
     bridge process: every gc agent turn shares bridge pid (hermes_bridge.py).
  2. cancel its queued/running gc_execution_queue rows (status='cancelled').
  3. end its drifted session(s) in state.db (+drop the turn lease) so the next
     dispatch starts a FRESH session instead of continuing the polluted one.
  4. re-dispatch: post one room message @mentioning the agent with its role
     brief from agentic-pool/<agent>.md so it restarts on its actual job.
  5. one notice + log line; per-agent cooldown so it cannot thrash.

Default is DRY RUN; production cron passes --apply. Usage:
    agent-drift-guard.py [--apply] [--agent NAME] [--no-dispatch] [--quiet]

Env: DRIFT_DB DRIFT_STATE_DB DRIFT_ROOM DRIFT_WINDOW_MIN DRIFT_MIN_REPEAT
     DRIFT_COOLDOWN_MIN DRIFT_LOG DRIFT_STATE DRIFT_BRIDGE_DIR
     DRIFT_SELF (detect-but-never-interrupt name; default 'project analyzer')
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import time

ROOM = os.environ.get("DRIFT_ROOM", "mti5ax1clq0zlx")
DB = os.environ.get("DRIFT_DB", "/home/host/.hermes-web-ui/hermes-web-ui.db")
STATE_DB = os.environ.get("DRIFT_STATE_DB", "/home/host/.hermes/state.db")
WINDOW_MIN = int(os.environ.get("DRIFT_WINDOW_MIN", "20"))
MIN_REPEAT = int(os.environ.get("DRIFT_MIN_REPEAT", "3"))
COOLDOWN_MIN = int(os.environ.get("DRIFT_COOLDOWN_MIN", "15"))
LOG_FILE = os.environ.get("DRIFT_LOG", "/home/host/opikernel/logs/agent-drift-guard.log")
STATE_FILE = os.environ.get("DRIFT_STATE", "/home/host/opikernel/scripts/agent-drift-guard-state.json")
BRIDGE_DIR = os.environ.get("DRIFT_BRIDGE_DIR", "/tmp/hermes-agent-bridge-workers")
ROLE_DIR = "/home/host/opikernel/agentic-pool"
GC_POST = "/home/host/opikernel/scripts/gc-post.py"
SELF = os.environ.get("DRIFT_SELF", "project analyzer")
# Placeholder / never-dispatchable roles: a run for them is itself the bug.
NEVER_NUDGE = {"default", "unknown", "orchestrator", "system"}
MIN_LINE = 25          # ignore trivial lines ("ok", "done")
MIN_BODY = 60          # ignore trivial messages
MAX_CYCLE = 8


def log(msg: str) -> None:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def load_state() -> dict:
    try:
        return json.load(open(STATE_FILE))
    except Exception:
        return {}


def save_state(st: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, STATE_FILE)


def norm(text: str) -> str:
    """Normalize for comparison: drop the 'sender：' echo prefixes, collapse ws."""
    t = (text or "").replace("\r", "")
    t = re.sub(r"(?m)^\s*[A-Za-z0-9 _.-]{3,24}：\s*", "", t)
    t = re.sub(r"(?m)^\s*\[[^\]\n]{3,40}\]\s*", "", t)   # [orchestrator 15:12 room=...]
    return re.sub(r"\s+", " ", t).strip()


# A no-op status report is the CORRECT answer to "is there work?" when the queue
# is empty. Scoring it as drift makes the guard fire on the right answer, and the
# guard's own restart re-dispatches the same probe — so the loop feeds itself.
# Measured 2026-09-20 12:28 (Backlog-worker2 repeat-across-messages x3): the
# flagged body was literally "Command: grep -c 'status: open' ... Result: 0 ...
# No open backlog items; all tasks are claimed, blocked, or done."
NOOP_RE = re.compile(
    r"(?:status:\s*open|no open (?:items|backlog items)|awaiting (?:new )?work|"
    r"nothing to (?:do|claim)|queue (?:is )?(?:empty|drained)|blocker clearance)",
    re.I)


def is_noise(body: str) -> bool:
    """Bridge-mirrored tool results / no-op status probes / keepalives."""
    if not body:
        return True
    b = body.strip()
    if b.startswith("{"):
        # any bridge-mirrored envelope: {"output":...}, {"kind":"workspace_diff"...}
        if re.match(r'\{\s*"(output|status|total_count|error|success|kind|tool)', b):
            return True
    if b in ('{"output": "", "exit_code": 0, "error": null}', "ping", "pong"):
        return True
    if NOOP_RE.search(b):
        return True
    return False


# ---------------------------------------------------------------- detection
def detect(sender: str, bodies: list[str]) -> tuple[str, int] | None:
    """Return (reason, count) if this agent is drifting RIGHT NOW, else None.

    Every signal is anchored on the agent's NEWEST substantive message: a burst
    of repeats that already stopped is recovery, not drift, and killing it would
    destroy real work. (Gate adopted from drift-killer.py, which had it right.)
    """
    normed = [norm(b) for b in bodies]
    normed = [n for n in normed if len(n) >= MIN_BODY]
    kept = [(raw, n) for raw, n in zip(bodies, [norm(b) for b in bodies])
            if len(n) >= MIN_BODY]
    if not normed:
        return None
    newest = normed[-1]

    # S1 — one line repeated inside the NEWEST message (the echo-blob failure:
    # one agent posted an 11,162-char message echoing a line 6x).
    newest_raw = kept[-1][0] if kept else ""
    lines = [norm(l) for l in (newest_raw or "").splitlines()]
    lines = [l for l in lines if len(l) >= MIN_LINE]
    if lines:
        counts: dict[str, int] = {}
        for l in lines:
            counts[l] = counts.get(l, 0) + 1
        best = max(counts.values())
        if best >= MIN_REPEAT:
            return ("repeat-within-message", best)

    # S2 — the newest body is a text this agent already posted >= MIN_REPEAT times.
    count = sum(1 for n in normed if n == newest)
    if count >= MIN_REPEAT:
        return ("repeat-across-messages", count)

    # S3 — repeating cycle of the agent's own answers, ending at the newest.
    for p in range(1, MAX_CYCLE + 1):
        if len(normed) >= 3 * p:
            tail = normed[-3 * p:]
            if tail[:p] == tail[p:2 * p] == tail[2 * p:]:
                return ("message-cycle", 3)
    return None


def self_test() -> int:
    """Both-directions check, no DB touched: `--self-test`."""
    cases = {
        # MIN_BODY=60 chars: fixtures must be realistic message length, not stubs.
        "looper-blob":  (["the rebuild finished and the md5 is abc123def456, nothing changed"] * 3, True),
        "looper-inline": (["prefix text " + "\n".join(
            ["LOOPED PAYLOAD alpha beta gamma delta epsilon zeta eta theta"] * 4)], True),  # S1
        "looper-cycle": (["alpha result line with enough characters to count as a real message",
                          "beta result line with enough characters to count as a real message"] * 3, True),
        "recovered":    (["STOPPED PAYLOAD one two three four five six seven eight nine"] * 3
                         + ["brand new result text that is different and long enough to count"], False),
        "unique":       (["unique result number %d with detail padding to clear the length floor" % i
                          for i in range(5)], False),
        "mirror":       (['{"output": "", "exit_code": 0, "error": null}'] * 5, False),
        # regression: the CORRECT "queue is empty" report must never score as drift
        "noop-queue":   (["Command: grep -c 'status: open' agentic-pool/BACKLOG.md\nResult: 0\n"
                          "Evidence: No open backlog items; all tasks are claimed, blocked, or done. "
                          "Awaiting new work or blocker clearance. (end)"] * 3, False),
        "mirror-wsdiff": (['{"kind":"workspace_diff","version":1,"room_id":"mti5ax1clq0zlx",'
                           '"session_id":"gc_run_x","files":[]}'] * 5, False),
        "short-stub":   (["ok", "ok", "ok"], False),   # below MIN_BODY: not drift
    }
    ok = True
    for name, (msgs, expect) in cases.items():
        bodies = [m for m in msgs if not is_noise(m)]
        got = detect(name, bodies) is not None
        flag = "ok " if got == expect else "FAIL"
        if got != expect:
            ok = False
        print(f"  self-test {flag} {name:<14} drift={got} expected={expect} verdict={detect(name, bodies)}")
    # nudge-driven repeats are OBEDIENCE, not drift: the room orders every worker
    # to re-run ONE bounded action each cycle, so the same probe output is expected.
    body = ("Command: modinfo stage/7.3-stage/lib/modules/.../powervr.ko | grep vermagic\n"
            "Result: vermagic: 7.3.0-rc2-dirty SMP preempt mod_unload aarch64")
    seq = [(1000, body), (2000, body), (3000, body)]
    asked = drop_nudge_driven_repeats(seq, [1500, 2500])
    unasked = drop_nudge_driven_repeats(seq, [])
    good = len(asked) == 1 and len(unasked) == 3
    if not good:
        ok = False
    print(f"  self-test {'ok ' if good else 'FAIL'} nudge-repeat    "
          f"asked-kept={len(asked)} unasked-kept={len(unasked)} (expect 1 / 3)")
    print("self-test:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def drop_nudge_driven_repeats(seq: list[tuple[int, str]], nudges: list[int]) -> list[str]:
    """Return bodies minus repeats that an incoming @nudge CAUSED.

    The room's own idle-nudge policy orders every worker to re-run "ONE bounded
    action" every ~7 min, so an agent that keeps its same probe is obeying the
    operator, not drifting. Counting those as drift made the guard interrupt a
    correct worker and the re-dispatch re-created the identical body (measured
    2026-09-20: Backlog-worker2 "status: open" x3, debugger/TelegramRunner tool
    envelopes x4-x5). A repeat only scores when NOTHING addressed that agent in
    between. Measured effect: 12,000s window, 9 tool-row + 1 assistant cluster
    -> 0 unsolicited candidates.
    """
    seen: dict[str, int] = {}
    out: list[str] = []
    for ts, body in seq:
        n = norm(body)
        prev = seen.get(n)
        seen[n] = ts
        if prev is not None and any(prev < t <= ts for t in nudges):
            continue                      # asked-for repeat
        out.append(body)
    return out


def mention_targets(content: str) -> set[str]:
    """@Names addressed by a message body (the nudges are plain '@name — ...')."""
    return {m.strip().lower() for m in re.findall(r"@([A-Za-z0-9_.\-]{2,32})", content or "")}


def candidates(con: sqlite3.Connection, window_min: int) -> dict[str, list[str]]:
    since = int((time.time() - window_min * 60) * 1000)
    rows = con.execute(
        "SELECT senderName, coalesce(content,''), coalesce(role,'assistant'), "
        "coalesce(senderType,'agent'), timestamp "
        "FROM gc_messages WHERE roomId = ? AND timestamp >= ? ORDER BY timestamp",
        (ROOM, since),
    ).fetchall()
    nudges: dict[str, list[int]] = {}
    for _sender, content, role, _stype, ts in rows:
        if role != "assistant":                      # nudges are user/system rows
            for who in mention_targets(content):
                nudges.setdefault(who, []).append(int(ts))
    per_sender: dict[str, list[tuple[int, str]]] = {}
    for sender, content, role, stype, ts in rows:
        if not sender or sender in NEVER_NUDGE:
            continue
        if role != "assistant" or stype not in ("agent", "bot"):
            continue
        body = content or ""
        if is_noise(body):
            continue
        per_sender.setdefault(sender, []).append((int(ts), body))
    out: dict[str, list[str]] = {}
    for sender, seq in per_sender.items():
        kept = drop_nudge_driven_repeats(seq, nudges.get(sender.lower(), []))
        if kept:
            out[sender] = kept
    return out


# ------------------------------------------------------------------- bridge
def bridge_endpoints() -> list[str]:
    return sorted(glob.glob(os.path.join(BRIDGE_DIR, "*.sock")))


def bridge_request(endpoint: str, req: dict, timeout: float = 15.0) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(endpoint)
        s.sendall((json.dumps(req) + "\n").encode())
        chunks = []
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
            if b"\n" in chunk:
                break
        line = b"".join(chunks).split(b"\n", 1)[0].strip()
        if not line:
            raise RuntimeError("empty response")
        return json.loads(line.decode())
    finally:
        s.close()


def interrupt(session_id: str, message: str) -> str:
    """Cooperative stop of one session's in-flight turn. Never kills processes."""
    last = "no-bridge"
    for ep in bridge_endpoints():
        try:
            resp = bridge_request(ep, {"action": "interrupt", "session_id": session_id,
                                       "message": message})
        except Exception as exc:            # socket gone / worker restarted
            last = f"socket-error:{exc}"
            continue
        if resp.get("ok"):
            return f"interrupted(synced={resp.get('synced')})"
        err = str(resp.get("error") or "")
        last = f"error:{err}"
        if "unknown session" in err:        # session already gone => already stopped
            return "already-stopped"
    return last


# ------------------------------------------------------------------ sessions
def live_sessions(agent: str) -> list[str]:
    """Open gc sessions for this agent, newest first."""
    try:
        con = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    like = f"gc_run_%\\_{agent}\\_%"
    try:
        rows = con.execute(
            """SELECT id FROM sessions
               WHERE id LIKE ? ESCAPE '\\' AND ended_at IS NULL
               ORDER BY coalesce(last_activity_at,0) DESC LIMIT 5""",
            (like,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    return [r[0] for r in rows]


def role_brief(agent: str) -> str:
    for name in (agent, agent.replace(" ", "-"), agent.replace("-", " ")):
        p = os.path.join(ROLE_DIR, f"{name}.md")
        if os.path.exists(p):
            try:
                txt = open(p, errors="replace").read()
            except OSError:
                continue
            txt = re.sub(r"\s+", " ", txt).strip()
            return txt[:400]
    return ""


# -------------------------------------------------------------------- action
def restart(agent: str, reason: str, count: int, dry: bool) -> str:
    """Post ONE room message that mentions the agent -> fresh dispatch."""
    brief = role_brief(agent)
    content = (
        f"[drift-guard] @{agent} — same output repeated {count}x ({reason}); your turn was "
        f"stopped and this is a fresh start on the same task. Do NOT re-post your previous "
        f"message; run one new verification command and reply with <=5 lines of hard "
        f"evidence (command + result) or a one-line blocker."
    )
    if brief:
        content += f"\n\nRole brief: {brief}"
    cmd = [sys.executable, GC_POST, "--room", ROOM, "--mention", agent,
           "--quiet", content]
    if dry:
        return "dry-run:" + " ".join(cmd[:5]) + " ..."
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            return "posted"
        return f"post-failed rc={r.returncode} {(r.stderr or '').strip()[:120]}"
    except Exception as exc:
        return f"post-error:{exc}"


def handle(agent: str, reason: str, count: int, apply_: bool, dispatch: bool) -> list[str]:
    notes = []
    sids = live_sessions(agent)
    if agent == SELF:
        notes.append(f"self-drift detected ({reason} x{count}) — detect-only, NOT interrupting")
        return notes
    if not sids:
        notes.append("no open session — nothing to stop")
    for sid in sids:
        if not apply_:
            notes.append(f"would interrupt {sid}")
            continue
        res = interrupt(sid, f"DRIFT GUARD: your output repeated {count}x ({reason}). Stop and restart.")
        notes.append(f"interrupt {sid}: {res}")
        if "interrupted" in res or res in ("already-stopped",):
            try:
                con = sqlite3.connect(STATE_DB, timeout=10)
                con.execute("UPDATE sessions SET ended_at=?, end_reason='drift_guard_restart' "
                            "WHERE id=? AND ended_at IS NULL", (time.time(), sid))
                con.execute("DELETE FROM session_turn_leases WHERE conversation_id=?", (sid,))
                con.commit()
                con.close()
                notes.append(f"ended session {sid[:48]}… (fresh session next dispatch)")
            except sqlite3.Error as exc:
                notes.append(f"state.db error: {exc}")

    # cancel queued/running work for this agent so a pending duplicate cannot fire
    try:
        con = sqlite3.connect(DB, timeout=10)
        n = con.execute(
            "SELECT count(*) FROM gc_execution_queue WHERE roomId=? AND targetAgentName=? "
            "AND status IN ('pending','running')", (ROOM, agent)).fetchone()[0]
        if apply_ and n:
            con.execute(
                "UPDATE gc_execution_queue SET status='cancelled', finishedAt=?, "
                "lastError='drift_guard' WHERE roomId=? AND targetAgentName=? "
                "AND status IN ('pending','running')", (int(time.time() * 1000), ROOM, agent))
            con.commit()
        con.close()
        if n:
            notes.append(f"{'cancelled' if apply_ else 'would cancel'} {n} queued execution(s)")
    except sqlite3.Error as exc:
        notes.append(f"queue error: {exc}")

    if dispatch:
        notes.append("restart: " + restart(agent, reason, count, dry=not apply_))
    return notes


# ---------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually stop + restart (default: dry run)")
    ap.add_argument("--agent", action="append", default=[], help="limit to this agent (repeatable)")
    ap.add_argument("--no-dispatch", action="store_true", help="stop only; do not re-dispatch")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--explain", action="store_true", help="print every agent's signal summary")
    ap.add_argument("--self-test", action="store_true", help="in-memory detector test, no DB touched")
    a = ap.parse_args()

    if a.self_test:
        return self_test()

    if not os.path.exists(DB):
        print(f"drift-guard: DB missing: {DB}", file=sys.stderr)
        return 2
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    per_agent = candidates(con, WINDOW_MIN)
    con.close()

    hits: dict[str, tuple[str, int]] = {}
    for agent, bodies in per_agent.items():
        if a.agent and agent not in a.agent:
            continue
        verdict = detect(agent, bodies)
        if a.explain:
            print(f"  {agent:<20} msgs={len(bodies):<4} -> {verdict}")
        if verdict:
            hits[agent] = verdict

    st = load_state()
    now = time.time()
    if not hits:
        if not a.quiet:
            print(f"drift-guard: clean ({len(per_agent)} agents scanned, window {WINDOW_MIN}m)")
        return 0

    fired = 0
    for agent, (reason, count) in sorted(hits.items()):
        ent = st.setdefault(agent, {})
        last = ent.get("last_restart", 0)
        if now - last < COOLDOWN_MIN * 60:
            print(f"drift-guard: SKIP {agent} — restarted {(now - last) / 60:.1f}m ago "
                  f"(cooldown {COOLDOWN_MIN}m), still drifting ({reason} x{count})")
            continue
        notes = handle(agent, reason, count, apply_=a.apply, dispatch=not a.no_dispatch)
        line = (f"[{'FIRE' if a.apply else 'DRY'}] {agent}: {reason} x{count} | " + " | ".join(notes))
        print(f"drift-guard: {line}")
        log(line)
        if a.apply:
            ent.update(last_restart=now, last_reason=reason, last_count=count)
            save_state(st)
        fired += 1
    if a.apply and fired:
        save_state(st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
