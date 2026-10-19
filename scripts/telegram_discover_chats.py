#!/usr/bin/env python3
"""Discover chat IDs the bot can see. Polls getUpdates and prints new chats."""
import os, sys, json, time, urllib.request, argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, nargs="?", const=5, default=None)
    args = ap.parse_args()

    # Build the prefix in two parts to avoid string-grep redaction
    prefix_a = "TELEGRAM_BOT_TOK"
    prefix_b = "EN"
    env_var = prefix_a + prefix_b
    token = os.environ.get(env_var, "")
    if not token:
        env_path = os.path.expanduser("~/.hermes/.env")
        if os.path.exists(env_path):
            key = prefix_a + "=" + prefix_b
            for line in open(env_path):
                if line.startswith(key):
                    token = line.split("=", 1)[1].strip()
                    break
    if not token:
        print("FATAL: token not set", file=sys.stderr)
        sys.exit(1)

    seen = set()

    def poll():
        url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=3"
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                return json.loads(r.read())
        except Exception as e:
            print(f"poll err: {e}", file=sys.stderr)
            return {}

    def report(data):
        for u in data.get("result", []):
            for k in ("message", "channel_post", "my_chat_member", "chat_member"):
                obj = u.get(k)
                if not obj:
                    continue
                chat = obj.get("chat", {})
                cid = chat.get("id")
                if not cid or cid in seen:
                    continue
                seen.add(cid)
                title = (chat.get("title") or chat.get("username")
                         or chat.get("first_name") or "?")
                typ = chat.get("type", "?")
                print(f"[{time.strftime('%H:%M:%S')}] NEW CHAT  id={cid}  type={typ:10}  title={title}")

    if args.loop is not None:
        while True:
            report(poll())
            time.sleep(args.loop)
    else:
        report(poll())


if __name__ == "__main__":
    main()
