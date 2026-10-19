#!/usr/bin/env python3
import time, os, sys

LOG="/home/host/opikernel/pvrgl-work/boot_min.log"
TTY="/dev/ttyACM0"

def log(m):
    print(m, flush=True)
    open(LOG,"a").write(f"[{time.strftime('%H:%M:%S')}] {m}\n")

log("START")
open(LOG,"w").write("")

# Fork ONLY
pid = os.fork()
if pid == 0:
    # Child: pure read loop, no signal handling
    fd = os.open(TTY, os.O_RDWR)
    f = open(LOG, "ab", 0)
    while True:
        d = os.read(fd, 4096)
        if d:
            f.write(d)
        else:
            time.sleep(0.1)
    os._exit(0)

log(f"Forked reader PID={pid}")
sys.exit(0)  # parent exits immediately
