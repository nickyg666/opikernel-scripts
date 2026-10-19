#!/usr/bin/env python3
"""Send SysRq keys to the opiz3w board over the serial console.

Why this exists: when the board wedges during boot there is no userspace, so
there is no shell to run `echo w > /proc/sysrq-trigger`. SysRq is handled in
interrupt context and still works - you send BREAK followed by the command
letter on the same tty.

    python3 sysrq.py t     task list of all CPUs
    python3 sysrq.py l     backtrace of all CPUs
    python6 sysrq.py w     blocked tasks
    python3 sysrq.py a     show backtrace of all CPUs (older alias for l)
    python3 sysrq.py w j   blocked tasks + stacks

Notes that cost time the hard way:
* The Pico bridge re-enumerates at 921600 baud. Pass --baud to override.
* The console often emits boot spew first; drain it before sending, or the
  reply is buried.
* Nothing is printed unless the kernel has
  CONFIG_MAGIC_SYSRQ enabled; if this returns nothing, the board is not that
  far along, and that is itself useful information.
"""
import argparse
import sys
import time

import serial

BAUD = 921600
PORT = "/dev/ttyACM0"
BREAK = b"\x1c"          # BREAK, which on a UART triggers SysRq


def drain(ser, seconds=2.0):
    """Consume pending console output so our reply isn't buried in boot spew."""
    end = time.time() + seconds
    n = 0
    while time.time() < end:
        try:
            chunk = ser.read(8192)
        except Exception:                              # noqa: BLE001
            chunk = b""
        n += len(chunk)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", help="SysRq letter(s), e.g. t, l, w")
    ap.add_argument("--baud", type=int, default=BAUD)
    ap.add_argument("--port", default=PORT)
    ap.add_argument("--settle", type=float, default=3.0,
                    help="seconds to wait for the reply after the last key")
    ap.add_argument("--pre-drain", type=float, default=2.0)
    args = ap.parse_args()

    ser = serial.Serial(args.port, args.baud, timeout=0.4)
    try:
        drain(ser, args.pre_drain)
        for k in args.keys:
            ser.write(BREAK)
            time.sleep(0.4)
            ser.write(k.encode())
            time.sleep(0.8)
        time.sleep(args.settle)
        # drain() returns a byte COUNT, not the payload. Read the bytes
        # separately, otherwise this crashes with 'int' has no .decode().
        buf = b""
        end = time.time() + 1.0
        while time.time() < end:
            try:
                buf += ser.read(8192)
            except Exception:                              # noqa: BLE001
                pass
        sys.stdout.write(buf.decode("utf-8", "replace"))
        sys.stdout.flush()
    finally:
        ser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
