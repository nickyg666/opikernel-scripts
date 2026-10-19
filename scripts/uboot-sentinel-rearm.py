#!/usr/bin/env python3
"""Keep exactly ONE armed U-Boot sentinel holding /dev/opiz3w-serial.

Why: pvrgl-work/uboot_armed.py --arm self-terminates when its window elapses
(state "window expired, no prompt"). Nothing re-arms it, so a card swap that
happens after expiry loses the U-Boot intercept (the capture that gives the
boot verdict). This guard re-arms WITHOUT ever power-cycling the board and
without ever starting a second reader.

Safety rules baked in:
  * flock -n on a dedicated lock: two guards can never race.
  * never start if a live `uboot_armed.py --arm` pid exists (port is owned).
  * never start if /dev/opiz3w-serial has a holder other than a stale lock owner.
  * never power-cycle: --arm performs no power action by design.
  * stop re-arming once a kernel banner was seen (kernel_seen true) or the
    lease is not ours.

Usage: uboot-sentinel-rearm.py --check     (cron entry, quiet unless it acts)
"""
import datetime
import fcntl
import json
import os
import re
import subprocess
import sys

ROOT = "/home/host/opikernel"
STATUS = os.path.join(ROOT, "pvrgl-work/uboot_armed_status.json")
LEASE = os.path.join(ROOT, "pvrgl-work/board.lease.json")
LOCK = "/tmp/uboot-sentinel-rearm.lock"
OWNER = "TelegramRunner"
WINDOW = 10800
NEW_WINDOW = 86400      # window used when we replace a sentinel (longer than any wait)
PREEMPT_MARGIN = 300    # replace a live sentinel this many seconds before it expires
REPLACE = os.path.join(ROOT, "scripts/sentinel-rearm-now.py")
POST = os.path.join(ROOT, "pvrgl-work/uboot_post_armed.txt")
LOG = os.path.join(ROOT, "pvrgl-work/uboot_sentinel_rearm.log")


def log(msg):
    with open(LOG, "a") as fh:
        fh.write("%s %s\n" % (subprocess.run(["date", "+%F_%T"], capture_output=True,
                                             text=True).stdout.strip(), msg))


def live_sentinel_pids():
    out = subprocess.run(["pgrep", "-f", "uboot_armed.py --arm"],
                         capture_output=True, text=True).stdout.split()
    pids = []
    for p in out:
        try:
            with open("/proc/%s/cmdline" % p, "rb") as fh:
                cmd = fh.read().decode("utf-8", "replace")
        except OSError:
            continue
        # skip our own shell/wrapper invocations
        if "rearm" in cmd or "hermes" in cmd or cmd.startswith("/bin/bash"):
            continue
        if "uboot_armed.py" in cmd and "--arm" in cmd:
            pids.append(p)
    return pids


def port_holder():
    r = subprocess.run(["sudo", "fuser", "/dev/opiz3w-serial"],
                       capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


def lease_owner():
    try:
        with open(LEASE) as fh:
            return json.load(fh).get("owner")
    except Exception:
        return None


def status():
    try:
        with open(STATUS) as fh:
            return json.load(fh)
    except Exception:
        return {}


def remaining():
    """Seconds left in the live sentinel's window, or None if unknown."""
    rec = status()
    try:
        a = datetime.datetime.strptime(rec["armed_at"], "%Y-%m-%d %H:%M:%S")
        end = a + datetime.timedelta(seconds=float(rec["window"]))
        return (end - datetime.datetime.now()).total_seconds()
    except Exception:
        return None


def holder_cmd(pid):
    try:
        return open("/proc/%s/cmdline" % pid, "rb").read().decode(
            "utf-8", "replace").replace("\x00", " ").strip()
    except OSError:
        return ""


def replace_sentinel(reason, explain=False):
    """TERM the current sentinel and arm a fresh long-window one (no power action)."""
    if explain:
        print("WOULD replace sentinel: %s" % reason)
        return 0
    log("REPLACE: %s" % reason)
    r = subprocess.run(["python3", REPLACE, str(NEW_WINDOW)], cwd=ROOT,
                       capture_output=True, text=True, timeout=180)
    log("REPLACE rc=%d out=%s" % (r.returncode, r.stdout.strip().replace("\n", " | ")))
    print("replaced sentinel (%s) rc=%d" % (reason, r.returncode))
    return 0


def main():
    explain = "--explain" in sys.argv
    if "--check" not in sys.argv and not explain:
        print(__doc__)
        return 0
    lf = open(LOCK, "w")
    try:
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0  # another guard is mid-flight

    holder = lease_owner()
    if holder != OWNER:
        log("skip: lease owner=%r not %s" % (holder, OWNER))
        return 0

    rec = status()
    if rec.get("kernel_seen"):
        log("skip: kernel banner already seen - intercept no longer needed")
        return 0

    pids = live_sentinel_pids()
    if pids:
        rem = remaining()
        if rem is not None and rem < PREEMPT_MARGIN:
            # Re-arm BEFORE expiry. Waiting for expiry hands the port to
            # serial_single_owner.py --ensure (60s cron), after which the
            # "port still held" branch below would skip forever and the
            # U-Boot intercept is silently gone.
            return replace_sentinel(
                "live sentinel %s expires in %.0fs (<%ds margin)"
                % (",".join(pids), rem, PREEMPT_MARGIN), explain)
        if explain:
            print("OK: sentinel %s armed, %.0fs of window left"
                  % (",".join(pids), rem if rem is not None else -1))
        return 0  # armed and holding: nothing to do, stay quiet

    ph = port_holder()
    if ph and "no process" not in ph:
        # fuser prints the pid GLUED to the device node ("2427011/dev/ttyACM1:"),
        # so splitting on whitespace finds no numeric token at all.
        held = re.findall(r"(\d+)(?=/)", ph) or [t for t in ph.split() if t.isdigit()]
        cmds = [holder_cmd(h) for h in held]
        perm = [h for h, c in zip(held, cmds) if "serial_single_owner" in c]
        if perm and len(perm) == len(held):
            return replace_sentinel(
                "port reclaimed from permanent owner pid(s) %s" % ",".join(perm), explain)
        log("skip: port still held by %r" % ph)
        return 0

    env = dict(os.environ, BOARD_LEASE_OWNER=OWNER)
    subprocess.Popen(
        ["python3", os.path.join(ROOT, "pvrgl-work/uboot_armed.py"),
         "--arm", "--window=%d" % WINDOW, "--post=%s" % POST],
        cwd=ROOT, env=env, stdout=open(LOG, "a"), stderr=subprocess.STDOUT,
        start_new_session=True)
    log("RE-ARMED sentinel window=%ds (previous state=%r)" % (WINDOW, rec.get("state")))
    print("re-armed: state was %r" % rec.get("state"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
