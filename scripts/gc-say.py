#!/usr/bin/env python3
"""gc-say — post a message into a Hermes group-chat room from RAW BASH.

Why this exists
---------------
`gc_post_message` is a *Hermes tool* (tui_gateway/methods_groups.py -> HostedRoomService).
It only exists inside a Hermes agent session, and the CLI has no `hermes tool call`
subcommand, so there is no way to reach it from a plain shell.

The group chat write path is in fact plain socket.io on the Hermes Web UI:
    POST /api/auth/login                      -> bearer token
    ws   /group-chat  (join -> message emit)   -> writes the message

This script does exactly that handshake, one-shot, and exits.  No Hermes session needed.

Usage
-----
    gc-say.py "hello room"
    gc-say.py --room mti5ax1clq0zlx "@all standup"
    echo "piped body" | gc-say.py -
    gc-say.py --read --limit 20          # read back the last 20 messages
    gc-say.py --whoami                   # probe login + ws handshake only

Env overrides: HERMES_WEBUI_URL, HERMES_WEBUI_USER, HERMES_WEBUI_PASS,
               GROUP_ROOM_ID, AGENT_SOCKET_SECRET
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

HERMES_URL = os.environ.get("HERMES_WEBUI_URL", "http://127.0.0.1:8648").rstrip("/")
HERMES_USER = os.environ.get("HERMES_WEBUI_USER", "admin")
HERMES_PASS = os.environ.get("HERMES_WEBUI_PASS", "123456")
GROUP_ROOM_ID = os.environ.get("GROUP_ROOM_ID", "mti5ax1clq0zlx")
AGENT_SOCKET_SECRET = os.environ.get(
    "AGENT_SOCKET_SECRET",
    "4f1fb429fd7731f2aceb43a3a051a6651632417a45f91102107f6edff264f771",
)
SENDER_NAME = os.environ.get("GC_SENDER_NAME", "bash")


def http_json(method: str, url: str, body=None, headers=None, timeout: float = 20.0):
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def login() -> str:
    r = http_json(
        "POST", f"{HERMES_URL}/api/auth/login",
        {"username": HERMES_USER, "password": HERMES_PASS},
    )
    tok = r.get("token") or (r.get("data") or {}).get("token")
    if not tok:
        raise SystemExit(f"FATAL: login returned no token: {r!r}")
    return tok


def read_room(token: str, room_id: str, limit: int = 20):
    url = (
        f"{HERMES_URL}/api/hermes/group-chat/rooms/{urllib.parse.quote(room_id)}"
        f"?{urllib.parse.urlencode({'limit': limit})}"
    )
    return http_json("GET", url, headers={"Authorization": f"Bearer {token}"})


def post_room(
    token: str,
    room_id: str,
    content: str,
    *,
    invite_code: str = "",
    mentions=None,
    timeout: int = 20,
) -> str:
    """Connect socket.io, join the room, emit one message, disconnect.

    Returns the message id that was sent.
    """
    try:
        import socketio  # provided by the Hermes venv
    except ImportError:
        raise SystemExit(
            "FATAL: python-socketio missing. Run this with the Hermes venv python:\n"
            "  /home/host/.hermes/hermes-agent/venv/bin/python3 " + __file__
        )

    sio = socketio.Client(reconnection=False)
    # The room protocol lives on the /group-chat *namespace*, and every call is an
    # ack-returning emit (client.call), not fire-and-forget. Auth is the bearer
    # token alone — the working reference is
    # ~/.hermes/plugins/group-chat-bridge/__init__.py (GroupChatClient._call).
    sio.connect(
        HERMES_URL,
        namespaces=["/group-chat"],
        auth={"token": token},
        transports=["websocket"],
        wait_timeout=timeout,
    )
    try:
        join = sio.call(
            "join",
            {"roomId": room_id, "name": SENDER_NAME, "description": "raw-bash group-chat poster",
             "historyLimit": 5},
            namespace="/group-chat",
            timeout=timeout,
        )
        if isinstance(join, dict) and join.get("error"):
            print(f"WARN: join rejected: {join['error']}", file=sys.stderr)
        msg_id = f"bash-{int(time.time() * 1000)}"
        res = sio.call(
            "message",
            {"roomId": room_id, "content": content, "id": msg_id},
            namespace="/group-chat",
            timeout=timeout,
        )
        if isinstance(res, dict) and res.get("error"):
            print(f"WARN: send rejected: {res['error']}", file=sys.stderr)
        time.sleep(0.15)          # let the frame flush before we tear down
        return msg_id
    finally:
        try:
            sio.disconnect()
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Post/read a Hermes group-chat room from raw bash.")
    ap.add_argument("content", nargs="?", help="message body; '-' reads stdin")
    ap.add_argument("--room", default=GROUP_ROOM_ID)
    ap.add_argument("--read", action="store_true", help="print the last N messages instead")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--grep", help="with --read, only print messages containing this substring")
    ap.add_argument("--whoami", action="store_true", help="login + ws handshake probe only")
    ap.add_argument("--json", action="store_true", help="raw JSON output")
    a = ap.parse_args()

    token = login()

    if a.whoami:
        print(f"login OK ({HERMES_URL} as {HERMES_USER})")
        try:
            info = read_room(token, a.room, 1)
            rooms = info.get("rooms") or info.get("data") or {}
            print(f"room read OK: {json.dumps(rooms)[:300]}")
        except urllib.error.HTTPError as e:
            print(f"room read FAILED: HTTP {e.code} {e.reason}")
        return 0

    if a.read:
        data = read_room(token, a.room, a.limit)
        if a.json:
            print(json.dumps(data, indent=2)[:20000])
            return 0
        msgs = data.get("messages") or data.get("events") or data.get("data") or []
        if isinstance(msgs, dict):
            msgs = msgs.get("messages") or msgs.get("events") or []
        if a.grep:
            msgs = [m for m in msgs if a.grep in str(m if not isinstance(m, dict) else m.get("content", ""))]
        for m in msgs[-a.limit:]:
            if not isinstance(m, dict):
                print(m)
                continue
            who = m.get("name") or m.get("sender") or m.get("userId") or m.get("role") or "?"
            body = (m.get("content") or m.get("text") or "").replace("\n", " ")
            print(f"[{who}] {body[:400]}")
        return 0

    content = a.content
    if content == "-" or (content is None and not sys.stdin.isatty()):
        content = sys.stdin.read().strip()
    if not content:
        ap.error("no content (pass a message or pipe stdin)")

    # inviteCode is required by the join contract; pull it live from the room.
    invite = os.environ.get("GROUP_INVITE_CODE", "")
    if not invite:
        try:
            invite = (read_room(token, a.room, 1).get("room") or {}).get("inviteCode", "")
        except Exception as e:  # noqa: BLE001
            print(f"WARN: could not read inviteCode ({e}); trying without", file=sys.stderr)

    msg_id = post_room(token, a.room, content, invite_code=invite)
    print(f"posted to {a.room} as {SENDER_NAME} (id={msg_id}): {content[:120]}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.HTTPError as e:
        print(f"FATAL: HTTP {e.code} {e.reason} from {e.url}", file=sys.stderr)
        sys.exit(2)
