#!/usr/bin/env python3
"""Paced U-Boot command injector for pico /dev/ttyACM0 on host .168.
Usage: uboot_drive_host.py 'cmd1' 'cmd2' ...   (each cmd sent with newline, paced)
Reads response into a log file after sending.
"""
import sys, time, os, subprocess

PORT = "/dev/ttyACM0"
LOG = "/home/host/pvrgl-work/uboot_drive.log"

cmds = sys.argv[1:] if len(sys.argv) > 1 else ["version"]

# write to port (needs root)
def write_port(s):
    with open(PORT, "wb") as f:
        f.write(s.encode())
    time.sleep(0.25)

def read_port(dur):
    out = b""
    end = time.time() + dur
    try:
        with open(PORT, "rb") as f:
            import select
            while time.time() < end:
                r, _, _ = select.select([f], [], [], 0.5)
                if r:
                    chunk = f.read(4096)
                    if chunk:
                        out += chunk
    except Exception as e:
        out += f"\n[read err {e}]".encode()
    return out

with open(LOG, "ab") as logf:
    for c in cmds:
        logf.write(f"\n>>> {c}\n".encode())
        write_port("\n")
        write_port(c + "\n")
        resp = read_port(1.2)
        logf.write(resp)
        sys.stdout.write(f">>> {c}\n{resp.decode(errors='replace')}\n")
        sys.stdout.flush()
        time.sleep(0.3)

print(f"[logged {LOG}]")
