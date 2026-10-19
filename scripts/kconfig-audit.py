#!/usr/bin/env python3
"""Append-only audit log for deliberate config edits, with agent attribution.

Why this exists
---------------
`kdir-build.sh` reads gold from `state/gold.config` and restores `.config` from it
whenever the two disagree. That is a safety net, but on 2026-09-28 it silently
discarded a legitimate `CONFIG_AW_RFKILL=m -> y` edit twice, produced a
byte-identical Image, and still reported `rc=0`. Two builds lost.

The build script now shouts instead of silently reverting, but shouting is not
enough on its own: the operator still has to work out *who* made a change and
*why*. A guard that reverts an edit destroys the evidence along with the edit.

So every deliberate change records an entry here BEFORE the file is touched:
who did it (Hermes session id, model, source), when, which symbol, old -> new,
and a free-text rationale. The build script's guard reads this log to decide
whether a `.config`/gold divergence is expected (a recorded, intentional change
in flight) or suspicious (drift nobody declared). Expected divergence is
allowed; undeclared drift is what gets flagged.

The log is JSONL: one object per line, append-only, and every entry carries the
session id so a conversation can be pulled straight back up with
`hermes sessions` / `session_search`.

    kconfig-audit.py set  CONFIG_AW_RFKILL m y "chip-en must probe at boot"
    kconfig-audit.py log  [--symbol CONFIG_AW_RFKILL] [--limit 20]
    kconfig-audit.py show <entry_id>
    kconfig-audit.py blame CONFIG_AW_RFKILL
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import sqlite3
import subprocess
import sys

KDIR = os.environ.get("KDIR", "/home/host/kernel-trees/host-build/mainline-7.3")
GOLD = os.environ.get("GOLD", "/home/host/opikernel/state/gold.config")
CFG = os.path.join(KDIR, ".config")
LOG = os.environ.get("KCONFIG_AUDIT_LOG", "/home/host/opikernel/state/kconfig-audit.jsonl")
STATE_DB = os.environ.get("HERMES_STATE_DB", "/home/host/.hermes/state.db")


# --------------------------------------------------------------------------
# attribution
# --------------------------------------------------------------------------
def _latest_session():
    """Best-effort id of the session doing the work right now.

    Preference order: an explicit env var, then the most recently started
    session that is still open. Attribution is best-effort by design - a build
    must never fail because a session id could not be resolved. The entry
    records which method was used so a weak attribution is visible.
    """
    for var in ("HERMES_SESSION_ID", "HERMES_SESSION"):
        v = os.environ.get(var)
        if v:
            return v, "env:%s" % var
    # Working dir is .hermes/workspace/<session-id> for CLI/TUI runs.
    cwd = os.getcwd()
    base = os.path.basename(cwd.rstrip("/"))
    if base.startswith("session_") or (len(base) > 10 and base.replace("_", "").isalnum()):
        return base, "cwd"
    try:
        con = sqlite3.connect("file:%s?mode=ro" % STATE_DB, uri=True, timeout=3)
        row = con.execute(
            "SELECT id FROM sessions ORDER BY started_at DESC LIMIT 1").fetchone()
        con.close()
        if row:
            return row[0], "db:latest"
    except Exception:                                      # noqa: BLE001
        pass
    # Last resort: the most recently written session file on disk.
    files = sorted(glob.glob("/home/host/.hermes/sessions/session_*.json"),
                   key=os.path.getmtime, reverse=True)
    if files:
        return os.path.basename(files[0])[len("session_"):-len(".json")], "file"
    return "unknown", "none"


def _session_meta(sid):
    meta = {}
    try:
        con = sqlite3.connect("file:%s?mode=ro" % STATE_DB, uri=True, timeout=3)
        row = con.execute(
            "SELECT source, model, message_count FROM sessions WHERE id=?",
            (sid,)).fetchone()
        con.close()
        if row:
            meta = {"source": row[0], "model": row[1], "messages": row[2]}
    except Exception:                                      # noqa: BLE001
        pass
    return meta


def _host():
    try:
        return subprocess.run(["hostname"], capture_output=True, text=True,
                              timeout=3).stdout.strip()
    except Exception:                                      # noqa: BLE001
        return "?"


# --------------------------------------------------------------------------
# reading the config files
# --------------------------------------------------------------------------
def read_val(path, key):
    try:
        with open(path, errors="replace") as f:
            for line in f:
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip()
                if line.strip() == "# %s is not set" % key:
                    return "n"
    except OSError:
        pass
    return None


def append(entry):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def load_all():
    out = []
    try:
        with open(LOG, errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return out


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------
def cmd_set(args):
    key, new = args.symbol, args.value
    gold_old = read_val(GOLD, key)
    cfg_old = read_val(CFG, key)
    sid, how = _latest_session()

    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "host": _host(),
        "session_id": sid,
        "session_source": how,
        "actor": "hermes-agent",
        "event": "kconfig-set",
        "symbol": key,
        "old": gold_old,
        "new": new,
        "gold_before": gold_old,
        "config_before": cfg_old,
        "gold_path": GOLD,
        "config_path": CFG,
        "rationale": args.reason or "",
        "pid": os.getpid(),
    }
    entry.update(_session_meta(sid))
    append(entry)
    print("audit: %s %s->%s  entry %s"
          % (key, gold_old, new, entry["session_id"][:12]))
    return 0


def cmd_log(args):
    rows = load_all()
    if args.symbol:
        rows = [r for r in rows if r.get("symbol") == args.symbol]
    for r in rows[-args.limit:][::-1]:
        print("%s  %-34s %-28s %s->%s  %s"
              % (r.get("ts", "?")[:19], r.get("session_id", "?")[:34],
                 r.get("symbol", "?"), r.get("old"), r.get("new"),
                 (r.get("rationale") or "")[:60]))
    return 0


def cmd_blame(args):
    rows = [r for r in load_all() if r.get("symbol") == args.symbol]
    if not rows:
        print("no audit entries for %s" % args.symbol)
        return 1
    r = rows[-1]
    print("symbol   : %s" % r["symbol"])
    print("change   : %s -> %s" % (r.get("old"), r.get("new")))
    print("when     : %s" % r.get("ts"))
    print("session  : %s   (via %s)" % (r.get("session_id"), r.get("session_source")))
    if r.get("model"):
        print("model    : %s" % r["model"])
    if r.get("source"):
        print("platform : %s" % r["source"])
    print("host     : %s" % r.get("host"))
    print("why      : %s" % (r.get("rationale") or "(none recorded)"))
    print()
    print("pull that conversation up with:")
    print("  session_search  --session %s" % r.get("session_id"))
    return 0


def cmd_show(args):
    for r in load_all():
        if r.get("id") == args.entry_id or r.get("session_id", "").startswith(args.entry_id):
            print(json.dumps(r, indent=2, sort_keys=True))
            return 0
    print("no such entry: %s" % args.entry_id)
    return 1


def cmd_pending(args):
    """Symbols with a recorded intent whose gold value does not match it yet."""
    latest = {}
    for r in load_all():
        if r.get("event") == "kconfig-set":
            latest[r["symbol"]] = r
    bad = 0
    for sym, r in sorted(latest.items()):
        have = read_val(GOLD, sym)
        if have != r.get("new"):
            bad += 1
            print("PENDING %-32s want=%-4s gold=%-4s  session %s"
                  % (sym, r.get("new"), have, r.get("session_id", "?")[:12]))
    if not bad:
        print("no pending config intents")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("set", help="record an intended symbol change (call BEFORE editing)")
    p.add_argument("symbol")
    p.add_argument("value", choices=["y", "m", "n"])
    p.add_argument("--reason", "-r", default="",
                   help="why - this is what you read months later")
    p.set_defaults(fn=cmd_set)

    p = sub.add_parser("log", help="show recent entries")
    p.add_argument("--symbol")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(fn=cmd_log)

    p = sub.add_parser("blame", help="who last changed a symbol, and why")
    p.add_argument("symbol")
    p.set_defaults(fn=cmd_blame)

    p = sub.add_parser("show", help="dump entries matching an id or session prefix")
    p.add_argument("entry_id")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("pending", help="recorded intents not yet reflected in gold")
    p.set_defaults(fn=cmd_pending)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
