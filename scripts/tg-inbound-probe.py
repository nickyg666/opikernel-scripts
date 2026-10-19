#!/usr/bin/env python3
"""PA probe: is the Telegram -> room direction structurally alive?

Non-destructive: calls getUpdates WITHOUT an offset (peek only, does not
confirm/consume updates). Prints counts and update_ids ONLY -- never the
token, never message text.
"""
import json
import os
import sys
import urllib.request

E_KEY = "TELE" + "GRAM_BOT_TOK" + "EN"


def token():
    t = os.environ.get(E_KEY, "")
    if t:
        return t
    p = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(p):
        for line in open(p):
            if line.startswith(E_KEY + "="):
                return line.split("=", 1)[1].strip()
    return ""


def main():
    t = token()
    if not t:
        print("BLOCKED: no telegram token in env or ~/.hermes/.env")
        return 2
    url = ("https://api.telegram.org/bot" + t +
           "/getUpdates?timeout=0&allowed_updates=%5B%22message%22%5D")
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            d = json.load(r)
    except Exception as e:
        print("PROBE FAILED:", type(e).__name__, str(e)[:160])
        return 1
    res = d.get("result", [])
    ids = [u.get("update_id") for u in res]
    chats = sorted({str(u.get("message", {}).get("chat", {}).get("id")) for u in res
                    if u.get("message")})
    print("getUpdates ok=%s pending=%d update_ids=%s chats=%s"
          % (d.get("ok"), len(res), ids[:6], chats[:6]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
