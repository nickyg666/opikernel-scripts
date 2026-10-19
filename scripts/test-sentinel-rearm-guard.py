#!/usr/bin/env python3
"""Logic tests for the re-arm guard's decision table (no port/power side effects).

Covers the 2026-09-20 defect: a guard that could only re-arm AFTER expiry would
find the port already taken by serial_single_owner.py and skip forever.
"""
import importlib.util
import json
import os
import sys
import tempfile

GUARD = "/home/host/opikernel/scripts/uboot-sentinel-rearm.py"
spec = importlib.util.spec_from_file_location("guard", GUARD)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

fails = []


def run(name, expect, *, pids, status, holder, cmd, argv=("--explain",)):
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(status, tmp)
    tmp.close()
    guard.STATUS = tmp.name
    guard.live_sentinel_pids = lambda: list(pids)
    guard.port_holder = lambda: holder
    guard.holder_cmd = lambda pid: cmd
    guard.lease_owner = lambda: "TelegramRunner"
    guard.log = lambda m: None
    sys.argv = ["guard"] + list(argv)
    import io
    real_stdout = sys.stdout
    buf = io.StringIO()
    sys.stdout = buf
    guard.main()
    sys.stdout = real_stdout
    got = buf.getvalue().strip()
    os.unlink(tmp.name)
    ok = expect in got
    print("%-46s %-6s got=%r" % (name, "PASS" if ok else "FAIL", got[:90]))
    if not ok:
        fails.append(name)
    return got


future = guard.datetime.datetime.now() + guard.datetime.timedelta(seconds=80000)
past = guard.datetime.datetime.now() - guard.datetime.timedelta(seconds=1000)

run("live sentinel, plenty of window -> no action",
    "OK: sentinel", pids=["111"],
    status={"state": "ARMED", "armed_at": future.strftime("%Y-%m-%d %H:%M:%S"),
            "window": 86400, "kernel_seen": False},
    holder="111/dev/ttyACM1:", cmd="python3 uboot_armed.py --arm")

run("live sentinel, 200s left -> PREEMPT replace",
    "WOULD replace sentinel", pids=["111"],
    status={"state": "ARMED", "armed_at": past.strftime("%Y-%m-%d %H:%M:%S"),
            "window": 1200, "kernel_seen": False},
    holder="111/dev/ttyACM1:", cmd="python3 uboot_armed.py --arm")

run("no sentinel, port held by permanent owner -> RECLAIM",
    "port reclaimed from permanent owner", pids=[],
    status={"state": "window expired, no prompt", "armed_at": past.strftime("%Y-%m-%d %H:%M:%S"),
            "window": 10800, "kernel_seen": False},
    holder="555/dev/ttyACM1:", cmd="python3 /home/host/opikernel/pvrgl-work/serial_single_owner.py")

run("no sentinel, port held by foreign pipeline -> leave it alone",
    "", pids=[],
    status={"state": "window expired", "armed_at": past.strftime("%Y-%m-%d %H:%M:%S"),
            "window": 10800, "kernel_seen": False},
    holder="777/dev/ttyACM1:", cmd="python3 scripts/manual_boot.py")

run("kernel banner seen -> never touch anything",
    "", pids=[],
    status={"state": "ARMED", "armed_at": past.strftime("%Y-%m-%d %H:%M:%S"),
            "window": 10800, "kernel_seen": True},
    holder="555/dev/ttyACM1:", cmd="python3 serial_single_owner.py")

print("\nRESULT: %s (%d/%d)" % ("FAIL " + ",".join(fails) if fails else "ALL PASS",
                               5 - len(fails), 5))
sys.exit(1 if fails else 0)
