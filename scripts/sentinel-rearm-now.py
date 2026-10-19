#!/usr/bin/env python3
"""Replace the armed U-Boot sentinel with a fresh, long-window one — NOW.

Why this exists (defect found 2026-09-20 14:32):
  uboot_armed.py --arm self-terminates when its window elapses (state
  "window expired, no prompt").  scripts/uboot-sentinel-rearm.py was believed to
  self-heal past expiry, but its re-arm path contains:

      ph = port_holder()
      if ph and "no process" not in ph:
          log("skip: port still held by %r" % ph); return 0

  serial_single_owner.py --ensure runs every 60s and takes the port as soon as
  the sentinel drops its .serial_exclusive.lock, so the guard then logs
  "skip: port still held" forever => the intercept is dead, exactly the failure
  it was written to prevent.  Re-arming BEFORE expiry with a window longer than
  the wait removes the gap entirely.

Does: TERM the current sentinel -> wait for the port to be free -> clear a stale
exclusive lock -> arm a new sentinel --window=<hours>.  Never powers the board.
"""
import json
import os
import subprocess
import sys
import time

ROOT = "/home/host/opikernel"
PORT = "/dev/opiz3w-serial"
LOCK = os.path.join(ROOT, "pvrgl-work/.serial_exclusive.lock")
STATUS = os.path.join(ROOT, "pvrgl-work/uboot_armed_status.json")
POST = os.path.join(ROOT, "pvrgl-work/uboot_post_armed.txt")
LOG = os.path.join(ROOT, "pvrgl-work/uboot_sentinel_rearm.log")
WINDOW = int(sys.argv[1]) if len(sys.argv) > 1 else 86400


def port_holder():
    r = subprocess.run(["sudo", "fuser", PORT], capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


def sentinel_pids():
    out = subprocess.run(["pgrep", "-f", "uboot_armed.py --arm"],
                         capture_output=True, text=True).stdout.split()
    pids = []
    for p in out:
        try:
            cmd = open("/proc/%s/cmdline" % p, "rb").read().decode("utf-8", "replace")
        except OSError:
            continue
        if "uboot_armed.py" in cmd and "--arm" in cmd:
            pids.append((p, cmd.replace("\x00", " ").strip()))
    return pids


def perm_owner_pids():
    """The permanent reader (serial_single_owner.py) is NOT a sentinel, so the TERM
    loop above skips it and the free-wait then times out forever (measured
    2026-09-20 16:15: guard reported 'port reclaimed from permanent owner 3035167'
    and rearm-now ABORTed every 3 min => intercept dead, json still 'ARMED').
    TERM it too: while the fresh sentinel holds .serial_exclusive.lock, the owner's
    `--ensure` cron will not spawn a second reader."""
    r = subprocess.run(["sudo", "fuser", PORT], capture_output=True, text=True)
    pids = []
    for t in (r.stdout + " " + r.stderr).split():
        if not t.isdigit():
            continue
        try:
            cmd = open("/proc/%s/cmdline" % t, "rb").read().decode("utf-8", "replace")
        except OSError:
            continue
        if "serial_single_owner.py" in cmd:
            pids.append((t, cmd.replace("\x00", " ").strip()))
    return pids


def main():
    print("before:", port_holder() or "(no process)")
    for pid, cmd in sentinel_pids() + perm_owner_pids():
        print("TERM", pid, cmd[:80])
        subprocess.run(["kill", "-TERM", pid], check=False)

    free = False
    for _ in range(45):
        h = port_holder()
        if not any(c.isdigit() for c in h):
            free = True
            break
        time.sleep(1)
    print("port after TERM:", port_holder() or "(no process)", "free=%s" % free)
    if not free:
        print("ABORT: port still held, not arming (would be a second reader)")
        return 1

    if os.path.exists(LOCK):
        txt = open(LOCK).read().split()
        stale = True
        if txt:
            try:
                os.kill(int(txt[0]), 0)
                stale = False
            except Exception:
                pass
        if stale:
            os.remove(LOCK)
            print("removed stale lock", txt)
        else:
            print("lock held by live pid", txt[0], "- leaving it")

    env = dict(os.environ, BOARD_LEASE_OWNER="TelegramRunner")
    subprocess.Popen(
        ["python3", os.path.join(ROOT, "pvrgl-work/uboot_armed.py"),
         "--arm", "--window=%d" % WINDOW, "--post=%s" % POST],
        cwd=ROOT, env=env, stdout=open(LOG, "ab"), stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, start_new_session=True)
    time.sleep(6)

    print("after:", port_holder() or "(no process)")
    print("sentinel pids:", [p for p, _ in sentinel_pids()])
    try:
        rec = json.load(open(STATUS))
        print("status:", {k: rec.get(k) for k in
                          ("state", "armed_at", "window", "bytes", "kernel_seen")})
    except Exception as exc:
        print("status unreadable:", exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
