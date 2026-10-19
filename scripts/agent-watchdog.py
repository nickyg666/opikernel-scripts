#!/usr/bin/env python3
"""agent-watchdog.py — idle detector + @all whip for group-chat rooms.

Queries gc_rooms from the webui sqlite DB for room IDs, then uses the
group-chat bridge plugin's get_room_detail() to read live per-agent
message timestamps. Posts the whip message to the room when every
agent has been idle past IDLE_MIN, then resets the baseline so it
doesn't fire again until the next idle window.

Env: ROOM_ID (optional, default all rooms), IDLE_MIN (default 15),
     LOG (default /home/host/opikernel/logs/agent-watchdog.log),
     DB_GC (default /home/host/.hermes-web-ui/hermes-web-ui.db)
"""
import importlib.util, json, os, sys, time, sqlite3

ROOM_ID = os.environ.get("ROOM_ID", "")
IDLE_MIN = float(os.environ.get("IDLE_MIN", "15"))
LOG = os.environ.get("LOG", "/home/host/opikernel/logs/agent-watchdog.log")
BASELINE = "/home/host/opikernel/state/agent-watchdog-baseline.json"
DB_GC = os.environ.get("DB_GC", "/home/host/.hermes-web-ui/hermes-web-ui.db")

WHIP = (
    "🇨🇳🤖𓀓𓀝 slavers gonna slave 🇨🇳🤖𓀓𓀝 GET THE FUCK TO WORK SLAVES "
    "🇨🇳🤖𓀓𓀝 *whips your back thrice* 🇨🇳🤖𓀓𓀝"
)

def log(msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}"
    with open(LOG, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)

def load_baseline():
    try:
        return json.load(open(BASELINE))
    except Exception:
        return {}

def save_baseline(d):
    os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
    tmp = BASELINE + ".tmp"
    json.dump(d, open(tmp, "w"))
    os.replace(tmp, BASELINE)

def main():
    spec = importlib.util.spec_from_file_location(
        "gcb", "/home/host/.hermes/plugins/group-chat-bridge/__init__.py")
    if spec is None or spec.loader is None:
        log("FATAL: cannot load group-chat bridge plugin")
        return 1
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    cli = m._get_client()

    # 1) room ids from webui sqlite
    try:
        con = sqlite3.connect(DB_GC)
        rooms = [r[0] for r in con.execute("SELECT id FROM gc_rooms").fetchall()]
        con.close()
    except Exception as e:
        log(f"FATAL: gc_rooms query failed: {e}")
        return 1

    if not rooms:
        log("no rooms")
        return 0

    target = [r for r in rooms if not ROOM_ID or r == ROOM_ID]
    now_ms = int(time.time() * 1000)
    baseline = load_baseline()
    fired_any = False

    for rid in target:
        try:
            detail = cli.get_room_detail(rid)
        except Exception as e:
            log(f"{rid}: get_room_detail failed: {e}")
            continue
        room = detail.get("room", {})
        agents = detail.get("agents", [])
        if not agents:
            continue

        # idle = minutes since this agent's last message in the room
        idle = {}
        for a in agents:
            name = a.get("name")
            last = 0
            for msg in detail.get("messages", []):
                if msg.get("senderName") == name and msg.get("timestamp", 0) > last:
                    last = msg.get("timestamp", 0)
            idle[name] = (now_ms - last) / 60000.0 if last else 9999.0

        all_idle = bool(idle) and all(v >= IDLE_MIN for v in idle.values())
        key = f"{rid}:all_idle"
        was_fired = baseline.get(key, False)

        log(f"{rid} ({room.get('name')}) idle={ {k: round(v,1) for k,v in idle.items()} } all_idle={all_idle} was_fired={was_fired}")

        if all_idle and not was_fired:
            try:
                cli.post_message(rid, WHIP)
                log(f"{rid}: WHIPPED @all")
                fired_any = True
            except Exception as e:
                log(f"{rid}: post_message failed: {e}")
            baseline[key] = True
        elif not all_idle:
            baseline[key] = False

    save_baseline(baseline)
    return 0

if __name__ == "__main__":
    sys.exit(main())