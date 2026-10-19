#!/usr/bin/env python3
"""Phase 1: Fork reader + power cycle + U-Boot intercept. Saves state to /tmp/boot_p1.state"""
import time, serial, sys, os

TTY="/dev/ttyACM0"; BAUD=115200
LOG="/home/host/opikernel/pvrgl-work/boot_p1.log"
STATE="/tmp/boot_p1.state"

def log(m):
    open(LOG,"w").write(f"[{time.strftime('%H:%M:%S')}] {m}\n")
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

log("=== P1: Reader + power + intercept ===")

# Fork reader (survives parent death)
pid=os.fork()
if pid==0:
    os.setsid()
    fd=os.open(TTY, os.O_RDWR|os.O_NOCTTY)
    f=open(LOG,"ab",0)
    while 1:
        r=os.read(fd,4096)
        if r: f.write(r); f.flush()
        else: time.sleep(.1)
    sys.exit(0)
log(f"Reader PID={pid}")
time.sleep(1)

# Power cycle
log("Power off")
os.system("/home/host/smartplug.py off"); time.sleep(9)
log("Power on")
os.system("/home/host/smartplug.py on")

# Wait port
for i in range(20):
    if os.path.exists(TTY) and (os.stat(TTY).st_mode&0o170000)==0o020000:
        log(f"Port T+{i}s, settle 2s"); time.sleep(2); break
    time.sleep(1)
else:
    log("FAIL: no port"); sys.exit(1)

# Serial + break spam
s=serial.Serial(TTY,BAUD,timeout=1)
s.reset_input_buffer()
log("Break spam")
for _ in range(15): s.write(b'\r'); s.flush(); time.sleep(.25)
s.break_condition=True; time.sleep(.05); s.break_condition=False
time.sleep(1)
while s.in_waiting: s.read(s.in_waiting)

# Wait for U-Boot
dl=time.time()+18
in_shell=False
while time.time()<dl:
    if s.in_waiting:
        d=s.read(s.in_waiting); t=d.decode('latin-1','replace')
        for l in t.split('\r\n'):
            if l.strip(): print(f"  {l}", flush=True)
        if '=> ' in t or '# ' in t:
            log("U-Boot OK"); in_shell=True; break
    time.sleep(.05)
s.close()

# Save state
open(STATE,"w").write(f"OK\nREADER_PID={pid}\n")
log("Phase 1 DONE")
