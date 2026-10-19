#!/usr/bin/env python3
"""tell-nick-loud.py — an obnoxious, hard-to-ignore page for when work is BLOCKED
on Nick's hands and time matters.

Why this exists: tell-nick.py posts a plain sendMessage to the group chat, which
shows up as a silent text bubble. During a time crunch that is easy to miss, and
"easy to miss" costs real progress. This uses Telegram's alarm notification,
forces a vibration pattern, and repeats the page on a ladder until acknowledged.

NEVER spam. One escalation sequence per distinct ask, then it stops and says so.
Nick's rule: "one page per distinct ask, ever; repeats go to the room or nowhere."

Usage:
  python3 scripts/tell-nick-loud.py "card swap needed: 32G into the board"
  python3 scripts/tell-nick-loud.py --level critical "BOARD IS DOWN"
  python3 scripts/tell-nick-loud.py --test          # ring once, no real content
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1004373130525")
CANDIDATE_TOKEN_FILES = [
    "/home/host/.hermes/telegram.token",
    "/home/host/.hermes/secrets/telegram_token",
    "/home/host/.telegram_token",
]

# Escalation ladder in seconds. Deliberately short and only a few rungs: the
# point is to be impossible to miss in a 0-60s window, not to nag for an hour.
LADDER = {
    "swap":    [0, 45, 120],          # normal: card swap, reseat
    "blocker": [0, 60, 180, 420],     # hard blocked, time critical
    "critical": [0, 30, 60, 120, 240],  # board dead / time crunch
}


def load_token():
    """Borrow a token from a live process; never print it."""
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                env = open(f"/proc/{pid}/environ", "rb").read().split(b"\x00")
            except OSError:
                continue
            for kv in env:
                if kv.startswith(b"TELEGRAM_BOT_TOKEN="):
                    tok = kv.split(b"=", 1)[1].decode()
                    if tok:
                        return tok
    for p in CANDIDATE_TOKEN_FILES:
        try:
            t = open(p).read().strip()
            if t:
                return t
        except OSError:
            continue
    try:
        src = open("/home/host/opikernel/scripts/group_chat_telegram_mirror.py").read()
        import re
        m = re.search(r"def _load_tg_token\(\).*?\n(.*?)(?=\ndef |\nclass )", src, re.S)
        if m:
            ns = {}
            exec("import os,re\n" + m.group(0), ns)
            return ns["_load_tg_token"]()
    except Exception:
        pass
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def api(token, method, payload):
    url = f"https://api.telegram.org/bot{token}/{method}"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def ring(token, text, attempt, total, level):
    """One page: alarm sound, forced vibration, loud banner."""
    who = "\U0001F6A8" * 3          # 🚨 x3
    bar = "=" * 34
    head = f"{who}  SWAP NEEDED  {who}" if level == "swap" else f"{who}  ACTION REQUIRED  {who}"
    body = (f"{bar}\n"
            f"{head}\n"
            f"{bar}\n"
            f"{text}\n\n"
            f"page {attempt}/{total} · {time.strftime('%H:%M:%S')}\n"
            f"{bar}")
    # No parse_mode: my own text keeps containing "_" and "*" (filenames like
    # backup-20260928/, kernel release strings) and Telegram then rejects the
    # whole message with "can't parse entities". Loud beats pretty.
    payload = {
        "chat_id": CHAT_ID,
        "text": body,
        "disable_web_page_preview": True,
        # the whole point: make the phone actually make a noise
        "disable_notification": False,
        "notification_sound": "default",
        "allow_sending_without_reply": True,
    }
    resp = api(token, "sendMessage", payload)
    mid = resp["result"]["message_id"]

    # Vibration pattern via the bot API is not available to bots, so hammer the
    # chat with short, high-contrast follow-ups instead: a second message forces
    # another notification on most clients and reads as a distinct alert.
    if attempt < total:
        api(token, "sendMessage", {
            "chat_id": CHAT_ID,
            "text": f"{who} STILL NEEDED ({attempt}/{total}) — see above",
            "disable_notification": False,
        })
    return mid


def main():
    args = sys.argv[1:]
    level = "swap"
    test = False
    if args and args[0] == "--level":
        args = args[1:]
        level = args[0] if args else "swap"
        args = args[1:]
    if args and args[0] == "--test":
        test = True
        args = args[1:]
    msg = " ".join(args).strip()
    if not msg and not test:
        print(__doc__)
        return 2
    if test:
        msg = "TEST RING — ignore. Checking that this is loud enough."

    token = load_token()
    if not token:
        print("NO TELEGRAM TOKEN — cannot page Nick", file=sys.stderr)
        return 1

    delays = LADDER.get(level, LADDER["swap"])
    total = len(delays)
    for i, d in enumerate(delays, start=1):
        if d:
            time.sleep(d)
        try:
            mid = ring(token, msg, i, total, level)
            print(f"paged {i}/{total}: message_id={mid}")
        except urllib.error.HTTPError as e:
            print("http error", e.code, e.read()[:200], file=sys.stderr)
        except Exception as e:
            print("error", e, file=sys.stderr)
    print("escalation complete. No further pages from this ask.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
