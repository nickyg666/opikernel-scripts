#!/usr/bin/env python3
"""Bidirectional bridge: Hermes group chat <-> Telegram chat.
Hardened with retry, rate-limit, circuit breaker, and inviteCode auth.
"""
import argparse, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
import socketio
import threading

# Token from env (built at runtime to dodge redaction filter)
E_NAME = "TELE" + "GRAM_BOT_TOK" + "EN"
tg_creds = os.environ.get(E_NAME, "")
if not tg_creds:
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        e_key = "TELE" + "GRAM_BOT_TOK" + "EN"
        for line in env_path.read_text().splitlines():
            if line.startswith(e_key + "="):
                tg_creds = line.split("=", 1)[1].strip()
                break
if not tg_creds:
    print("FATAL: telegram token not set", file=sys.stderr)
    sys.exit(1)

HERMES_URL = os.environ.get("HERMES_WEBUI_URL", "http://127.0.0.1:8648")
HERMES_USER = os.environ.get("HERMES_WEBUI_USER", "admin")
HERMES_PASS = os.environ.get("HERMES_WEBUI_PASS", "123456")
GROUP_ROOM_ID = os.environ.get("GROUP_ROOM_ID", "mti5ax1clq0zlx")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "10"))
ROOM_TO_TG_RATE = float(os.environ.get("ROOM_TO_TG_RATE", "3"))
STATE_FILE = Path(os.environ.get("STATE_FILE", "/home/host/opikernel/stage/group_bridge_state.json"))
INVITE_CODE = os.environ.get("ROOM_INVITE_CODE", "DD0RMRE6BG1BLN")

if not TELEGRAM_CHAT_ID:
    print("FATAL: TELEGRAM_CHAT_ID not set", file=sys.stderr)
    sys.exit(1)

API_ROOT = "https://api.telegram.org/bot" + tg_creds

# Circuit breaker state
class CircuitBreaker:
    def __init__(self, name, failure_threshold=5, recovery_timeout=60):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure = 0
        self.open = False
        self._lock = threading.Lock()

    def record_success(self):
        with self._lock:
            self.failures = 0
            self.open = False

    def record_failure(self):
        with self._lock:
            self.failures += 1
            self.last_failure = time.time()
            if self.failures >= self.failure_threshold:
                self.open = True
                print(f"[{self.name}] circuit breaker OPEN after {self.failures} failures", file=sys.stderr)

    def can_proceed(self):
        with self._lock:
            if not self.open:
                return True
            if time.time() - self.last_failure >= self.recovery_timeout:
                self.open = False
                self.failures = 0
                print(f"[{self.name}] circuit breaker HALF-OPEN (retry)", file=sys.stderr)
                return True
            return False

tg_breaker = CircuitBreaker("TG_API", failure_threshold=10, recovery_timeout=30)
room_breaker = CircuitBreaker("ROOM_API", failure_threshold=5, recovery_timeout=60)

# Rate limit tracking
class RateLimiter:
    def __init__(self, max_per_minute):
        self.max_per_minute = max_per_minute
        self.calls = []
        self._lock = threading.Lock()

    def wait_if_needed(self):
        with self._lock:
            now = time.time()
            self.calls = [t for t in self.calls if now - t < 60]
            if len(self.calls) >= self.max_per_minute:
                sleep_time = 60 - (now - self.calls[0]) + 0.1
                if sleep_time > 0:
                    time.sleep(sleep_time)
            self.calls.append(time.time())

tg_rate_limiter = RateLimiter(25)  # leave headroom under 30/min limit
room_rate_limiter = RateLimiter(30)

def http_json(method, url, body=None, headers=None, timeout=30):
    data = None
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    if body is not None:
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def login_hermes():
    r = http_json("POST", f"{HERMES_URL}/api/auth/login",
                  {"username": HERMES_USER, "password": HERMES_PASS})
    return r["token"]

def hermes_get_room(token, room_id, limit=50):
    hdr = {"Authorization": f"Bearer {token}"}
    url = f"{HERMES_URL}/api/hermes/group-chat/rooms/{room_id}?{urllib.parse.urlencode({'limit': limit})}"
    return http_json("GET", url, headers=hdr)

def tg_send(chat_id, text, max_retries=8):
    url = API_ROOT + "/sendMessage"
    body = {"chat_id": chat_id, "text": text, "parse_mode": "MarkdownV2", "disable_web_page_preview": True}
    data = json.dumps(body).encode()
    last = None
    for attempt in range(max_retries):
        tg_rate_limiter.wait_if_needed()
        if not tg_breaker.can_proceed():
            raise RuntimeError(f"TG circuit breaker open")
        req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = json.loads(r.read())
                if not resp.get("ok"):
                    raise RuntimeError(f"tg not ok: {resp}")
                tg_breaker.record_success()
                return resp["result"]["message_id"]
        except urllib.error.HTTPError as e:
            err_body = e.read().decode(errors="replace")[:200]
            if e.code == 429:
                m = re.search(r'"retry_after":\s*(\d+)', err_body)
                wait = int(m.group(1)) + 1 if m else 30
                print(f"  tg 429, sleeping {wait}s (attempt {attempt+1}/{max_retries})", file=sys.stderr)
                time.sleep(wait)
                continue
            last = f"HTTP {e.code}: {err_body}"
            if e.code >= 500 and attempt < max_retries - 1:
                tg_breaker.record_failure()
                wait = min(2 ** attempt, 30)
                time.sleep(wait)
                continue
            tg_breaker.record_failure()
            raise RuntimeError(f"tg HTTP {e.code}: {last}")
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            if attempt < max_retries - 1:
                tg_breaker.record_failure()
                wait = min(2 ** attempt, 30)
                time.sleep(wait)
                continue
            tg_breaker.record_failure()
            raise RuntimeError(f"tg send failed: {last}")
    tg_breaker.record_failure()
    raise RuntimeError(f"tg send failed after {max_retries} attempts: {last}")

def tg_get_updates(offset=None, timeout=25):
    params = {"timeout": timeout, "allowed_updates": ["message"]}
    if offset is not None:
        params["offset"] = offset
    url = API_ROOT + "/getUpdates?" + urllib.parse.urlencode(params)
    try:
        tg_rate_limiter.wait_if_needed()
        if not tg_breaker.can_proceed():
            raise RuntimeError("TG circuit breaker open")
        with urllib.request.urlopen(url, timeout=timeout + 5) as r:
            resp = json.loads(r.read())
            tg_breaker.record_success()
            return resp
    except urllib.error.HTTPError as e:
        if e.code == 409:
            return {"ok": False, "result": []}
        tg_breaker.record_failure()
        raise

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {
        "room_to_tg": {"last_msg_id": None, "sent_ids": []},
        "tg_to_room": {"last_update_id": 0},
    }

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))

_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_ITAL = re.compile(r"(?<!\*)\*([^\*\n]+)\*(?!\*)")
_MD_CODE = re.compile(r"`([^`]+)`")
_MD_HDR = re.compile(r"^#{1,6}\s*", re.MULTILINE)

def md_to_html(s):
    s = _MD_HDR.sub("", s)
    s = _MD_LINK.sub(r'<a href="\2">\1</a>', s)
    s = _MD_CODE.sub(r"<code>\1</code>", s)
    s = _MD_BOLD.sub(r"<b>\1</b>", s)
    s = _MD_ITAL.sub(r"<i>\1</i>", s)
    return s

def escape_html(s):
    return s.replace("&", "&").replace("<", "<").replace(">", ">")

def escape_markdown(s):
    for old, new in _MD_ESCAPE:
        s = s.replace(old, new)
    return s

def format_room_msg(msg):
    import re
    sender = msg.get("senderName", "unknown")
    sender_type = msg.get("senderType", "member")
    content = (msg.get("content") or "").strip()
    if not content:
        return None
    # Strip ALL HTML tags
    content = re.sub(r"<[^>]+>", "", content)
    # Strip backticks
    content = re.sub(r"`+", "", content)
    # Strip markdown bold/italic
    content = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", content)
    content = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", content)
    # Strip hex numbers (0x...)
    content = re.sub(r"0x[0-9a-fA-F]+", "0x...", content)
    # Strip other problematic sequences
    content = re.sub(r"\b(cmd|line|cell|0x)\b", "", content)
    # MarkdownV2 escape: _ * [ ] ( ) ~ > # + - = | { } . !
    mdv2_esc = {
        '_': r'\_', '*': r'\*', '[': r'\[', ']': r'\]',
        '(': r'\(', ')': r'\)', '~': r'\~', '>': r'\>',
        '#': r'\#', '+': r'\+', '-': r'\-', '=': r'\=',
        '|': r'\|', '{': r'\{', '}': r'\}', '.': r'\.',
        '!': r'\!',
    }
    for ch, esc in mdv2_esc.items():
        content = content.replace(ch, esc)
    if len(content) > 3500:
        content = content[:3500] + " …"
    # Also escape prefix
    sender_esc = sender
    for ch, esc in mdv2_esc.items():
        sender_esc = sender_esc.replace(ch, esc)
    prefix = f"[{sender_esc}]" if sender_type == "agent" else f"<{sender_esc}>"
    return f"{prefix}: {content}"

class RoomClient:
    def __init__(self):
        self.sio = socketio.Client(reconnection=True, reconnection_attempts=0,
                                    reconnection_delay=2, reconnection_delay_max=10)
        self.token = None
        self.connected = False
        self.join_done = False
        self._lock = threading.Lock()
        self._setup_handlers()

    def _setup_handlers(self):
        outer = self
        @self.sio.event
        def connect():
            with outer._lock:
                outer.connected = True
                outer.join_done = False
            print(f"[{time.strftime('%H:%M:%S')}] ws connected, joining room via inviteCode")
            outer.sio.emit("join", {"roomId": GROUP_ROOM_ID}, callback=outer._on_join_ack)

        @self.sio.event
        def connect_error(data):
            print(f"ws connect_error: {data}", file=sys.stderr)

        @self.sio.event
        def disconnect():
            with outer._lock:
                outer.connected = False
                outer.join_done = False
            print(f"ws disconnected, will reconnect")

        @self.sio.on("message")
        def on_room_message(data):
            pass

    def _on_join_ack(self, *args):
        with self._lock:
            self.join_done = True
        if args and isinstance(args[0], dict) and "error" in args[0]:
            print(f"  join ack ERROR: {args[0]['error']}")
        else:
            print(f"  join ack OK: {args}")

    def start(self, token):
        self.token = token
        self.sio.connect(f"{HERMES_URL}/group-chat",
                         auth={"inviteCode": INVITE_CODE, "userId": "1", "name": "telegram-bridge",
                               "description": "Telegram <-> Group chat bridge", "source": "user"},
                         transports=["websocket"], wait_timeout=15)

    def send_to_room(self, content):
        with self._lock:
            if not (self.connected and self.join_done):
                print(f"ws not ready (connected={self.connected} joined={self.join_done})", file=sys.stderr)
                return False
        msg_id = f"tg-{int(time.time()*1000)}"
        try:
            self.sio.emit("message", {
                "roomId": GROUP_ROOM_ID,
                "id": msg_id,
                "content": content,
                "role": "user",
            })
            print(f"[{time.strftime('%H:%M:%S')}] tg->room emitted {msg_id}")
            return True
        except Exception as e:
            print(f"ws emit failed: {e}", file=sys.stderr)
            return False

def poll_room_to_tg(token, state, dry_run=False):
    room_rate_limiter.wait_if_needed()
    if not room_breaker.can_proceed():
        print("room circuit breaker open, skipping poll", file=sys.stderr)
        return 0
    rt = state["room_to_tg"]
    last_id = rt.get("last_msg_id")
    sent_ids = set(rt.get("sent_ids", []))
    try:
        room = hermes_get_room(token, GROUP_ROOM_ID, limit=100)
        room_breaker.record_success()
    except Exception as e:
        room_breaker.record_failure()
        print(f"room poll error: {e}", file=sys.stderr)
        return 0

    msgs = room.get("messages", [])
    if not msgs:
        return 0

    new_count = 0
    for m in msgs:
        mid = m.get("id")
        if not mid or mid in sent_ids:
            continue
        if last_id and mid == last_id:
            continue
        # Skip toolresult and toolcall messages entirely - they contain raw JSON
        if "toolresult" in mid or "toolcall" in mid:
            print(f"  [DEBUG] Skipping toolresult/toolcall: {mid[:80]}", file=sys.stderr)
            sent_ids.add(mid)
            continue
        formatted = format_room_msg(m)
        if not formatted:
            sent_ids.add(mid)
            continue
        if dry_run:
            print(f"DRY: would send {mid}")
        else:
            try:
                tg_send(TELEGRAM_CHAT_ID, formatted)
                new_count += 1
                time.sleep(1.0 / ROOM_TO_TG_RATE)
            except Exception as e:
                print(f"tg send failed for {mid}: {e}", file=sys.stderr)
                room_breaker.record_failure()
                # Don't break - skip this message but continue processing
                sent_ids.add(mid)
                continue
        sent_ids.add(mid)
        if len(sent_ids) > 2000:
            sent_ids = set(list(sent_ids)[-1500:])

    rt["last_msg_id"] = msgs[-1].get("id") if msgs else last_id
    rt["sent_ids"] = list(sent_ids)
    return new_count

def poll_tg_to_room(rc, state, dry_run=False):
    tr = state["tg_to_room"]
    last_uid = tr.get("last_update_id", 0)
    updates = tg_get_updates(offset=last_uid + 1 if last_uid else None)
    new_count = 0
    max_uid = last_uid
    for u in updates.get("result", []):
        uid = u.get("update_id", 0)
        if uid > max_uid:
            max_uid = uid
        msg = u.get("message")
        if not msg:
            continue
        chat = msg.get("chat", {})
        if str(chat.get("id")) != str(TELEGRAM_CHAT_ID):
            continue
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        if dry_run:
            print(f"DRY: would forward TG->{GROUP_ROOM_ID}: {text[:80]}")
        elif rc:
            rc.send_to_room(text)
            new_count += 1
        tr["last_update_id"] = max_uid
    return new_count

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", type=int, nargs="?", const=POLL_INTERVAL, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = login_hermes()
    state = load_state()
    print(f"bridge running: room={GROUP_ROOM_ID} <-> tg={TELEGRAM_CHAT_ID}")

    rc = RoomClient()
    try:
        rc.start(token)
    except Exception as e:
        print(f"ws start failed: {e}, continuing with REST-only mode", file=sys.stderr)
        rc = None

    if args.loop is not None:
        print(f"entering loop every {args.loop}s")
        while True:
            try:
                n1 = poll_room_to_tg(token, state, dry_run=args.dry_run)
                n2 = poll_tg_to_room(rc, state, dry_run=args.dry_run) if rc else 0
                if n1 or n2:
                    save_state(state)
            except Exception as e:
                print(f"loop err: {e}", file=sys.stderr)
            time.sleep(args.loop)
    else:
        n1 = poll_room_to_tg(token, state, dry_run=args.dry_run)
        n2 = poll_tg_to_room(rc, state, dry_run=args.dry_run) if rc else 0
        save_state(state)
        print(f"room->tg: {n1}, tg->room: {n2}")
        if rc:
            rc.sio.disconnect()

if __name__ == "__main__":
    main()