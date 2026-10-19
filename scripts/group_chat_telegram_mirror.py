#!/usr/bin/env python3
"""
Mirror Hermes Web-UI group chat messages to a Telegram channel.

Polls a group's REST endpoint for new messages and posts each new
message to a configured Telegram channel. State (last seen message
id) is persisted in a small JSON file so we don't re-send on restart.

Usage:
    python3 group_chat_telegram_mirror.py --once          # single poll cycle
    python3 group_chat_telegram_mirror.py --loop 10       # continuous (10s poll)
    python3 group_chat_telegram_mirror.py --once --dry-run  # preview only
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ---------- Config ----------
HERMES_URL = os.environ.get("HERMES_WEBUI_URL", "http://127.0.0.1:8648")
HERMES_USER = os.environ.get("HERMES_WEBUI_USER", "admin")
HERMES_PASS = os.environ.get("HERMES_WEBUI_PASS", "123456")
GROUP_ROOM_ID = os.environ.get("GROUP_ROOM_ID", "mti5ax1clq0zlx")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1004373130525")
STATE_FILE = Path(os.environ.get(
    "STATE_FILE",
    "/home/host/opikernel/stage/group_mirror_state.json"
))


def _load_tg_token():
    _BOT = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    if not _BOT:
        print('FATAL: TELEGRAM_BOT_TOKEN env var not set', file=sys.stderr)
        sys.exit(1)
    return _BOT


TG_TOKEN = _load_tg_token()


# ---------- HTTP helpers ----------
def http_json(method, url, body=None, headers=None):
    data = None
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    if body is not None:
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"{method} {url} -> {e.code}: {body}")


def login():
    r = http_json("POST", f"{HERMES_URL}/api/auth/login",
                  {"username": HERMES_USER, "password": HERMES_PASS})
    return r["token"]


def fetch_messages(token, room_id, limit=50):
    """Fetch latest messages from a room."""
    hdr = {"Authorization": f"Bearer {token}"}
    url = (f"{HERMES_URL}/api/hermes/group-chat/rooms/{room_id}"
           f"?{urllib.parse.urlencode({'limit': limit})}")
    r = http_json("GET", url, headers=hdr)
    return r["messages"], r.get("total", 0), r.get("hasMore", False)


def post_telegram(chat_id, text, max_retries=5):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    body = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    data = json.dumps(body).encode()
    last_err = None
    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = json.loads(r.read())
                if not resp.get("ok"):
                    raise RuntimeError(f"Telegram sendMessage not ok: {resp}")
                return resp["result"]["message_id"]
        except urllib.error.HTTPError as e:
            err_body = e.read().decode(errors="replace")[:200]
            # 429: rate limited — read retry_after
            if e.code == 429:
                import re as _re
                m = _re.search(r'"retry_after":\s*(\d+)', err_body)
                wait = int(m.group(1)) + 1 if m else 30
                last_err = f"429 retry {wait}s"
                if attempt < max_retries - 1:
                    time.sleep(wait)
                    continue
            last_err = f"HTTP {e.code}: {err_body}"
            if attempt < max_retries - 1 and e.code >= 500:
                time.sleep(2 ** attempt)
                continue
            break
    raise RuntimeError(last_err or "telegram send failed")


# ---------- State ----------
def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_msg_id": None, "sent_count": 0, "sent_ids": []}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ---------- Formatting ----------
EMOJI = {
    "member": "👤",
    "agent": "🤖",
    "system": "⚙️",
}

_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_ITAL = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_MD_CODE = re.compile(r"`([^`]+)`")
_MD_HDR = re.compile(r"^#{1,6}\s*", re.MULTILINE)


def escape_html(s):
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))


def md_to_html(s):
    s = _MD_HDR.sub("", s)
    s = _MD_LINK.sub(r'<a href="\2">\1</a>', s)
    s = _MD_CODE.sub(r"<code>\1</code>", s)
    s = _MD_BOLD.sub(r"<b>\1</b>", s)
    s = _MD_ITAL.sub(r"<i>\1</i>", s)
    return s


def format_message(msg):
    sender = msg.get("senderName", "unknown")
    sender_type = msg.get("senderType", "member")
    content = msg.get("content", "")
    if not content:
        return None
    emoji = EMOJI.get(sender_type, "•")
    if len(content) > 3500:
        content = content[:3400] + "\n…(truncated)"
    body = md_to_html(content)
    text = f"{emoji} <b>{escape_html(sender)}</b>\n{body}"
    return text


# ---------- Main ----------
def poll_once(token, dry_run=False, msg_delay=2.5):
    state = load_state()
    last_seen = state.get("last_msg_id")
    sent_ids = set(state.get("sent_ids", []))

    messages, total, has_more = fetch_messages(token, GROUP_ROOM_ID, limit=50)

    new_count = 0
    # Messages come back most-recent-first; iterate in reverse to send oldest-newest
    # Stop when we hit the last-seen id.
    new_msgs = []
    for msg in reversed(messages):
        mid = msg.get("id")
        if not mid:
            continue
        if last_seen and mid == last_seen:
            break
        if mid in sent_ids:
            continue
        new_msgs.append(msg)

    for msg in new_msgs:
        mid = msg["id"]
        text = format_message(msg)
        if not text:
            continue
        if dry_run:
            print(f"--- WOULD POST ({mid}) ---")
            print(text[:400])
            print()
        else:
            try:
                tg_id = post_telegram(TELEGRAM_CHAT_ID, text)
                print(f"sent {mid} -> tg {tg_id}")
            except Exception as e:
                print(f"FAILED {mid}: {e}", file=sys.stderr)
                continue
        sent_ids.add(mid)
        new_count += 1
        # Rate limit: stay under ~25 msg/min to avoid 429s
        time.sleep(msg_delay)

    if new_count and not dry_run:
        if new_msgs:
            state["last_msg_id"] = new_msgs[-1]["id"]
        state["sent_ids"] = list(sent_ids)[-500:]
        state["sent_count"] = state.get("sent_count", 0) + new_count
        state["last_poll"] = time.time()
        save_state(state)

    return new_count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", type=int, nargs="?", const=10, default=None,
                    help="Continuous poll (interval seconds)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--msg-delay", type=float, default=2.5,
                    help="Seconds between Telegram posts (default 2.5 = 24/min)")
    args = ap.parse_args()

    token = login()
    print(f"logged in, mirroring room {GROUP_ROOM_ID} -> tg {TELEGRAM_CHAT_ID}")

    if args.loop is not None:
        interval = args.loop
        while True:
            try:
                n = poll_once(token, dry_run=args.dry_run, msg_delay=args.msg_delay)
                if n:
                    print(f"[{time.strftime('%H:%M:%S')}] posted {n}")
            except Exception as e:
                print(f"poll error: {e}", file=sys.stderr)
            time.sleep(interval)
    else:
        n = poll_once(token, dry_run=args.dry_run, msg_delay=args.msg_delay)
        print(f"posted {n} new messages")


if __name__ == "__main__":
    main()
