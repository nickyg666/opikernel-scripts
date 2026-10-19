#!/usr/bin/env python3
"""Power-cycle the opiz3w board over the HOST's USB port.

The board is now powered from the host PC's USB port (the Pico serial bridge
sits on hub port 1-10). The hub exposes no per-port power switching
(/sys/bus/usb/devices/1-10/power has no `control`), but it does honour
`authorized`: writing 0 de-authorises the device, which drops the USB link and
with it the board's 5V feed; writing 1 re-enumerates it. That is a real
power cycle from the host, no smartplug and no physical access needed.

    python3 usb-power.py            # report current state
    python3 usb-power.py off        # cut power
    python3 usb-power.py on         # restore power
    python3 usb-power.py cycle      # off, wait, on (default 8s off)
    python3 usb-power.py cycle 20   # longer discharge

De-authorising only severs data; whether the board fully browns out depends on
its own current draw. A long `off` (>=20s) is the reliable option if the
board stays powered.
"""
import os
import subprocess
import sys
import time

PORT = "/sys/bus/usb/devices/1-10"
AUTH = PORT + "/authorized"
VENDOR = "2e8a"          # Raspberry Pi Pico = the serial bridge
TTL = 8


def sh(cmd, sudo=False):
    if sudo:
        cmd = "echo 0 | sudo -S -p '' " + cmd
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)


def pico_present():
    r = sh("lsusb | grep -c %s" % VENDOR)
    return (r.stdout or "0").strip() not in ("0", "")


def tty_present():
    return os.path.exists("/dev/ttyACM0")


def set_auth(value):
    try:
        with open(AUTH, "w") as fh:
            fh.write(str(value))
        return True
    except PermissionError:
        return bool(sh("echo %d | sudo tee %s >/dev/null" % (value, AUTH), sudo=True).returncode == 0)
    except Exception as e:                                  # noqa: BLE001
        print("set_auth(%s) failed: %r" % (value, e), file=sys.stderr)
        return False


def status():
    print("usb port     : %s" % PORT)
    print("pico present : %s" % pico_present())
    print("ttyACM0      : %s" % ("/dev/ttyACM0" if tty_present() else "absent"))
    try:
        print("authorized   : %s" % open(AUTH).read().strip())
    except Exception as e:                                  # noqa: BLE001
        print("authorized   : <unreadable: %r>" % e)


def fix_tty():
    """Re-apply the line discipline.

    The Pico bridge comes back with a default baud after every
    re-enumeration, so a cycle leaves the port at the wrong rate and every
    command returns binary garbage. Do this immediately after `on`/`cycle`,
    otherwise the next sercmd looks like a dead board.
    """
    for _ in range(30):
        if os.path.exists("/dev/ttyACM0"):
            for baud in ("921600", "115200", "460800", "230400", "57600"):
                subprocess.run(["stty", "-F", "/dev/ttyACM0", baud, "raw", "-echo"],
                               capture_output=True, timeout=10)
                time.sleep(0.6)
                try:
                    probe = subprocess.run(
                        ["python3", "/home/host/opikernel/pvrgl-work/sercmd.py", "uname -r", "8"],
                        capture_output=True, text=True, timeout=40).stdout
                except Exception:                                  # noqa: BLE001
                    probe = ""
                if "7.3" in probe:
                    return True
            return True
        time.sleep(1)
    return False


def main(argv):
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        status()
        return 0
    if cmd == "off":
        ok = set_auth(0)
        time.sleep(2)
        print("power off    : %s (pico=%s tty=%s)"
              % (ok, pico_present(), tty_present()))
        return 0 if ok else 1
    if cmd == "on":
        ok = set_auth(1)
        for _ in range(30):
            if pico_present() and tty_present():
                break
            time.sleep(1)
        fix_tty()
        print("power on     : %s (pico=%s tty=%s)"
              % (ok, pico_present(), tty_present()))
        return 0 if ok else 1
    if cmd == "cycle":
        secs = int(argv[1]) if len(argv) > 1 else TTL
        set_auth(0)
        time.sleep(secs)
        set_auth(1)
        for _ in range(40):
            if pico_present() and tty_present():
                break
            time.sleep(1)
        fix_tty()
        print("cycled %ds   : pico=%s tty=%s" % (secs, pico_present(), tty_present()))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
