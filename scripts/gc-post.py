#!/usr/bin/env python3
"""gc-post — post a message into a Hermes Web-UI group chat room from ANY bash shell.

No Hermes session, no hermes CLI, no plugin registry. Uses the same wire protocol
the group-chat-bridge plugin uses:

  1. POST {base}/api/auth/login            -> JWT
  2. socket.io connect {base}/group-chat   (auth={"token": JWT}, websocket transport)
  3. emit `join`    {roomId, name, description, historyLimit}
  4. emit `message` {roomId, content, id}

There is NO REST POST route for messages (verified 2026-09-18: POST
/api/hermes/group-chat/rooms/<id>/messages -> 404), so socket.io is the only path.

Usage
-----
  gc-post.py "hello room"                       # default room
  gc-post.py --room mti5ax1clq0zlx "@all hi"
  echo "text" | gc-post.py -                    # stdin
  gc-post.py --as "project analyzer" "text"
  gc-post.py --list                             # list rooms
  gc-post.py --history 20                       # last 20 messages (REST GET)

Exit codes: 0 ok, 1 usage, 2 login failed, 3 socket failed, 4 post rejected.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

DEFAULT_BASE = os.environ.get("GC_BASE_URL", "http://127.0.0.1:8648")
DEFAULT_ROOM = os.environ.get("GC_ROOM_ID", "mti5ax1clq0zlx")
DEFAULT_USER = os.environ.get("GC_USER", "admin")
DEFAULT_PASS = os.environ.get("GC_PASS", "123456")
DEFAULT_NAME = os.environ.get("GC_NAME", "kernel-orchestrator")
DEFAULT_PROFILE = os.environ.get("GC_PROFILE", "default")


def login(base: str, user: str, password: str, profile: str) -> str:
    body = json.dumps({"username": user, "password": password}).encode()
    req = urllib.request.Request(
        f"{base}/api/auth/login",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Hermes-Profile": profile,
        },
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read())
    tok = data.get("token") or data.get("access_token")
    if not tok:
        raise RuntimeError(f"no token in login response: {list(data)[:8]}")
    return tok


def get_json(url: str, token: str, profile: str) -> dict:
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}", "X-Hermes-Profile": profile}
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())


def room_roster(base: str, token: str, room: str, profile: str) -> list[dict]:
    """Agent rows for a room: [{name, agentId, id}, ...].

    Structured mentions are validated server-side against gc_room_agents:
      participantId must be the row's agentId, displayName must equal name,
      and the content must contain a real '@name' token.
    """
    d = get_json(f"{base}/api/hermes/group-chat/rooms/{room}", token, profile)
    out = []
    for a in d.get("agents") or []:
        if a.get("name") and a.get("agentId"):
            out.append(a)
    return out


WEDGE_TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lane-wedge-check.py")


def wedged_lanes(room: str) -> set[str]:
    """Names whose (roomId, agentId) drain key is stuck — the shared predicate.

    A mention of one of these is accepted by the server, queued in memory and
    NEVER shifted: the row sits at status='queued' forever and the post is a
    no-op that also amplifies the backlog.  Fail-open (empty set) if the tool
    is missing/broken, and say so — silence here is what let 25 undelivered
    rows pile up on 2026-09-20.
    """
    try:
        r = subprocess.run(["python3", WEDGE_TOOL, "--room", room, "--names-only"],
                           capture_output=True, text=True, timeout=8)
    except Exception as exc:  # noqa: BLE001
        print(f"[gc-post] WEDGE GUARD UNAVAILABLE ({exc}) — mentions unfiltered", file=sys.stderr)
        return set()
    if r.returncode not in (0, 1):
        print(f"[gc-post] WEDGE GUARD rc={r.returncode} — mentions unfiltered", file=sys.stderr)
        return set()
    return {n.strip() for n in r.stdout.splitlines() if n.strip()}


def resolve_mentions(roster: list[dict], names: list[str], content: str,
                     wedged: set[str] | None = None) -> tuple[list[dict], list[str]]:
    """Map role names -> structured mentions. Returns (mentions, errors).

    Names whose drain key is wedged are dropped (text still carries '@name',
    but no structured mention is sent) so no caller can re-inject into a stuck
    key.  Operators get one line per dropped lane on stderr.
    """
    wedged = wedged or set()
    by_name = {a["name"].lower(): a for a in roster}
    mentions, errors = [], []
    for n in names:
        row = by_name.get(n.strip().lower())
        if not row:
            errors.append(f"unknown agent '{n}' (not in room roster)")
            continue
        if row["name"] in wedged:
            print(f"[gc-post] WEDGE GUARD: dropped structured mention of '{row['name']}' "
                  f"(drain key stuck — it would never be delivered)", file=sys.stderr)
            continue
        if not mention_token_present(content, row["name"]):
            errors.append(
                f"content has no VALID '@{row['name']}' token — the server accepts a mention only "
                f"when the char before '@' is not [A-Za-z0-9_] and the char right AFTER the name is "
                f"whitespace, end-of-text, or one of . , ! ? ; : ， 。 ！ ？ ； ： ) ] }} > . "
                f"e.g. \"@{row['name']}'s\" is INVALID and kills the whole post."
            )
            continue
        mentions.append({"type": "agent", "participantId": row["agentId"],
                         "displayName": row["name"]})
    return mentions, errors


# Trailing characters the web-ui accepts after an @mention (mirrors `x4n` in
# hermes-web-ui dist/server/index.js) -- plus whitespace and end-of-string.
MENTION_TAIL = set(".,!?;:，。！？；：)]}>")


def mention_token_present(content: str, name: str) -> bool:
    """Exact mirror of the server's `pye()` matcher.

    The server REJECTS THE WHOLE MESSAGE ("Invalid structured mentions") if any
    one mention fails, so a naive substring check here lets a post silently die:
    "@build-engineer's" contains "@build-engineer" but is not a mention token.
    """
    hay = content.lower()
    needle = f"@{name.lower()}"
    start = 0
    while True:
        i = hay.find(needle, start)
        if i < 0:
            return False
        before_ok = i == 0 or not (content[i - 1].isalnum() or content[i - 1] == "_")
        j = i + len(needle)
        after_ok = j >= len(content) or content[j].isspace() or content[j] in MENTION_TAIL
        if before_ok and after_ok:
            return True
        start = i + 1


def post_message(base: str, token: str, room: str, content: str,
                 name: str, profile: str, history_limit: int = 5,
                 mentions: list[dict] | None = None) -> dict:
    import socketio  # type: ignore

    sio = socketio.Client(logger=False, engineio_logger=False)
    result: dict = {}

    @sio.on("connect", namespace="/group-chat")
    def _on_connect():  # noqa: D401
        print("[gc-post] socket connected ns=/group-chat", file=sys.stderr)

    @sio.on("connect_error", namespace="/group-chat")
    def _on_err(data):
        print(f"[gc-post] connect_error: {data}", file=sys.stderr)

    sio.connect(
        f"{base}/group-chat",
        namespaces=["/group-chat"],
        auth={"token": token},
        transports=["websocket"],
        wait_timeout=10,
        headers={"X-Hermes-Profile": profile},
    )
    try:
        joined = sio.call(
            "join",
            {"roomId": room, "name": name, "description": "", "historyLimit": history_limit},
            namespace="/group-chat",
            timeout=10,
        )
        print(f"[gc-post] join ack: {json.dumps(joined)[:200]}", file=sys.stderr)

        msg_id = f"gcbash-{int(time.time() * 1000)}-{os.urandom(3).hex()}"
        payload: dict = {"roomId": room, "content": content, "id": msg_id}
        if mentions:
            payload["mentions"] = mentions
        ack = sio.call(
            "message",
            payload,
            namespace="/group-chat",
            timeout=10,
        )
        result = {"ok": True, "roomId": room, "id": msg_id,
                  "mentions": [m["displayName"] for m in (mentions or [])], "ack": ack}
        # The server acks rejections as {"error": ...} instead of raising; treat as failure
        # (e.g. "Agent mentions require structured metadata", "Invalid structured mentions").
        if isinstance(ack, dict) and ack.get("error"):
            result["ok"] = False
            print(f"[gc-post] SERVER REJECTED: {ack['error']}", file=sys.stderr)
    finally:
        try:
            sio.disconnect()
        except Exception:
            pass
    return result


def main() -> int:
    ap = argparse.ArgumentParser(prog="gc-post", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("content", nargs="?", help="message text, or '-' for stdin")
    ap.add_argument("--room", default=DEFAULT_ROOM)
    ap.add_argument("--as", dest="sender", default=DEFAULT_NAME)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--user", default=DEFAULT_USER)
    ap.add_argument("--password", default=DEFAULT_PASS)
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--list", action="store_true", help="list rooms and exit")
    ap.add_argument("--history", "--read", dest="history", type=int, nargs="?", const=20,
                    metavar="N", help="print last N messages and exit (alias: --read, default 20)")
    ap.add_argument("--limit", type=int, help="alias for the read count (with --read)")
    ap.add_argument("--grep", help="filter read output by substring/regex")
    ap.add_argument("--whoami", action="store_true", help="login + probe, then exit")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--mention", action="append", default=[], metavar="ROLE",
                    help="structured @mention of a room agent (repeatable). The content MUST "
                         "contain '@ROLE'; the server rejects an unbacked mention.")
    ap.add_argument("--mention-dev", action="append", default=[], metavar="ID",
                    help="debug: inject a raw participantId (validation testing)")
    a = ap.parse_args()

    try:
        token = login(a.base, a.user, a.password, a.profile)
    except Exception as exc:
        print(f"[gc-post] LOGIN FAILED: {exc}", file=sys.stderr)
        return 2

    if a.whoami:
        print(f"login OK ({a.base} as {a.user})")
        try:
            d = get_json(f"{a.base}/api/hermes/group-chat/rooms/{a.room}", token, a.profile)
            room = d.get("room", d)
            msgs = d.get("messages") or []
            print(f"room read OK: {room.get('name')} ({len(msgs)} messages)")
            print(f"agents: {[x.get('name') for x in (d.get('agents') or [])]}")
        except Exception as exc:
            print(f"room read FAILED: {exc}", file=sys.stderr)
            return 3
        return 0

    if a.history is None and a.limit is not None:
        a.history = a.limit
    if a.history is None and a.grep:
        a.history = 50

    if a.list:
        try:
            data = get_json(f"{a.base}/api/hermes/sessions/hermes/groups", token, a.profile)
            for g in data.get("groups", []):
                for s in g.get("sessions", []):
                    print(f"{s.get('id')}\t{s.get('title')}\t{s.get('message_count')} msgs")
        except Exception as exc:
            print(f"[gc-post] list failed: {exc}", file=sys.stderr)
            return 3
        return 0

    if a.history:
        try:
            d = get_json(f"{a.base}/api/hermes/group-chat/rooms/{a.room}", token, a.profile)
            import re as _re
            for m in (d.get("messages") or [])[-a.history:]:
                who = m.get("senderName") or m.get("agentName") or m.get("sender") or "?"
                body = (m.get("content") or "").replace("\n", " ")[:160]
                if a.grep:
                    try:
                        if not _re.search(a.grep, (m.get("content") or "")):
                            continue
                    except _re.error:
                        if a.grep not in (m.get("content") or ""):
                            continue
                print(f"{who}: {body}")
        except Exception as exc:
            print(f"[gc-post] history failed: {exc}", file=sys.stderr)
            return 3
        return 0

    content = a.content
    if content is None:
        ap.print_help()
        return 1
    if content == "-":
        content = sys.stdin.read().strip()
    if not content:
        print("[gc-post] refusing to post empty content", file=sys.stderr)
        return 1

    mentions: list[dict] = []
    if a.mention or a.mention_dev:
        try:
            roster = room_roster(a.base, token, a.room, a.profile)
        except Exception as exc:
            print(f"[gc-post] roster fetch failed: {exc}", file=sys.stderr)
            return 3
        mentions, errors = resolve_mentions(roster, a.mention, content,
                                           wedged=wedged_lanes(a.room))
        if errors:
            for e in errors:
                print(f"[gc-post] MENTION REJECTED: {e}", file=sys.stderr)
            return 1
        # debug escape hatch: bypass the content-token check but still send a
        # WELL-FORMED mention. The server validates every mention object and
        # rejects the WHOLE message ("Invalid structured mentions") when
        # displayName is not the room roster's real name for that participantId
        # -- passing the raw id as displayName silently killed the post.
        roster_name = {a["agentId"]: a["name"] for a in roster}
        for i in a.mention_dev:
            if i not in roster_name:
                print(f"[gc-post] MENTION REJECTED: no room agent with "
                      f"participantId '{i}'", file=sys.stderr)
                return 1
            mentions.append({"type": "agent", "participantId": i,
                             "displayName": roster_name[i]})

    try:
        res = post_message(a.base, token, a.room, content, a.sender, a.profile,
                           mentions=mentions or None)
    except Exception as exc:
        print(f"[gc-post] SOCKET/POST FAILED: {exc}", file=sys.stderr)
        return 3
    if not a.quiet:
        print(json.dumps(res, indent=2)[:800])
    return 0 if res.get("ok") else 4


if __name__ == "__main__":
    sys.exit(main())
