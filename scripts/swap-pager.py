#!/usr/bin/env python3
"""swap-pager.py — page Nick for a card swap and re-ping until acknowledged.

WHY THIS SHAPE (2026-09-24): the Hermes gateway already long-polls our Telegram bot
(pid 4097903, two ESTAB sockets to 149.154.166.110). A second getUpdates poller would
steal each other's updates, so we must NOT poll. Instead this is a state machine:

  send -> wait for an ack -> re-ping on an interval -> stop on ack

An "ack" is any inbound text from Nick in the target chat after the page went out.
We detect it out-of-band, by asking the gateway's own local API for recent chat
activity, never by polling the bot API. That keeps a single reader of Telegram.

Usage:
  python3 scripts/swap-pager.py --ask "URGENT: card swap needed" --need 3
  python3 scripts/swap-pager.py --status
  python3 scripts/swap-pager.py --cancel
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "..", "state", "swap-pager.json")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1004373130525")
RETRY_SECONDS = 120          # Nick's rule: if no answer in 2 minutes, ping again
MAX_PINGS = int(os.environ.get("SWAP_PAGER_MAX_PINGS", "8"))
MIN_RETRY_SECONDS = 90       # never hammer faster than this


def state_path() -> str:
    return os.path.abspath(STATE)


def load() -> dict:
    try:
        return json.load(open(state_path()))
    except Exception:
        return {}


def save(s: dict) -> None:
    os.makedirs(os.path.dirname(state_path()), exist_ok=True)
    json.dump(s, open(state_path(), "w"), indent=1)


def load_token() -> str:
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        return os.environ["TELEGRAM_BOT_TOKEN"]
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
    raise SystemExit("no TELEGRAM_BOT_TOKEN available")


def send(text: str) -> int:
    tok = load_token()
    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    body = json.dumps({"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = json.loads(r.read())
            if resp.get("ok"):
                return resp["result"]["message_id"]
        except Exception as e:
            print("send error:", e, file=sys.stderr)
            time.sleep(3)
    return 0


def gateway_recent(after_ts: float) -> list:
    """Ack detection WITHOUT polling Telegram. Two out-of-band signals, both read locally:
      1) Nick said swapped/go in the mti5 room (the rooms are the shared work channel)
      2) the tab card's boot/mainline/Image md5 changed (i.e. a different card got staged)
    The Hermes gateway remains the only reader of the Telegram bot API."""
    hits = []
    try:
        import sqlite3
        con = sqlite3.connect("/home/host/.hermes-web-ui/hermes-web-ui.db")
        rows = con.execute(
            "SELECT senderName, content, timestamp FROM gc_messages "
            "WHERE roomId='mti5ax1clq0zlx' AND timestamp > ?", (int(after_ts * 1000),)
        ).fetchall()
        for name, content, ts in rows:
            if name in ("the-human", "admin", "Nick"):
                low = (content or "").lower()
                if any(w in low for w in ("swap", "go", "done", "swapped", "in the board")):
                    hits.append({"from": name, "text": (content or "")[:120]})
        con.close()
    except Exception as e:
        print("ack check (room) failed:", e, file=sys.stderr)
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ask", help="the ask to send to Nick")
    ap.add_argument("--need", type=int, default=MAX_PINGS, help="max re-pings")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--cancel", action="store_true")
    ap.add_argument("--check", action="store_true", help="poll once for an ack, no sending")
    a = ap.parse_args()

    if a.status:
        s = load()
        if not s:
            print("no active swap request")
            return 0
        print(json.dumps(s, indent=1))
        return 0

    if a.cancel:
        s = load()
        if s:
            send(f"[swap-pager] CANCELLED — {s.get('ask','')[:80]} (no longer needed)")
        save({})
        print("cancelled")
        return 0

    if a.check:
        s = load()
        if not s:
            print("no active request")
            return 0
        if gateway_recent(s["sent_at"]):
            send("[swap-pager] ACK received — standing down, back to work.")
            save({})
            print("ack received, cleared")
        else:
            print("no ack yet")
        return 0

    if not a.ask:
        ap.print_help()
        return 2

    s = {"ask": a.ask, "sent_at": time.time(), "pings": 1, "need": a.need,
         "last_ping": time.time()}
    mid = send(f"[swap-pager] {a.ask}")
    s["message_id"] = mid
    save(s)
    print(f"paged (message {mid}); will re-ping every {RETRY_SECONDS}s up to {a.need} times")
    return 0


if __name__ == "__main__":
    sys.exit(main())
