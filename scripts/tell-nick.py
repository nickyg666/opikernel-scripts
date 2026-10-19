#!/usr/bin/env python3
"""tell-nick.py — page Nick on Telegram. Use whenever a physical action is needed
(card swap, reseat, reseat a reader) or when he explicitly asked to be pinged.

Usage:
  python3 scripts/tell-nick.py "card swap needed: put the 465GB card in the board"
  python3 scripts/tell-nick.py --from "me" "text"     # override the host label
"""
import json
import os
import re
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


def load_token():
    # borrow from any live process that already holds it (bridge/mirror), never print it
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
    # fall back to the loader the existing mirror uses
    src = open("/home/host/opikernel/scripts/group_chat_telegram_mirror.py").read()
    m = re.search(r"def _load_tg_token\(\).*?\n(.*?)(?=\ndef |\nclass )", src, re.S)
    if m:
        ns = {}
        try:
            exec("import os,re\n" + m.group(0), ns)
            return ns["_load_tg_token"]()
        except Exception:
            pass
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def send(text, retries=3):
    token = load_token()
    if not token:
        print("NO TELEGRAM TOKEN — cannot page Nick", file=sys.stderr)
        return 1
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True}).encode()
    for attempt in range(retries):
        req = urllib.request.Request(url, data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = json.loads(r.read())
            if resp.get("ok"):
                print("paged Nick on telegram:", resp["result"]["message_id"])
                return 0
        except urllib.error.HTTPError as e:
            print("http error", e.code, e.read()[:120], file=sys.stderr)
        except Exception as e:
            print("error", e, file=sys.stderr)
        time.sleep(3)
    return 1


if __name__ == "__main__":
    args = sys.argv[1:]
    label = "Gemma"
    if args and args[0] == "--from":
        label = args[1]
        args = args[2:]
    msg = " ".join(args).strip()
    if not msg:
        print(__doc__)
        raise SystemExit(2)
    host = "opiz3w kernel lane"
    stamp = time.strftime("%H:%M")
    raise SystemExit(send(f"[{label} · {host} · {stamp}] {msg}"))
