#!/usr/bin/env python3
"""Chunk 1: Fork reader + power cycle + U-Boot intercept."""
import time, os, sys, select, fcntl

TTY="/dev/ttyACM0"; LOG="/home/host/opikernel/pvrgl-work/boot_c1.log"
TIOCSBRK=0x5427; TIOCCBRK=0x5428

def log(m):
    print(m, flush=True)
    open(LOG,"a").write(f"[{time.strftime('%H:%M:%S')}] {m}\n")

# Fork reader
pid = os.fork()
if pid == 0:
    for attempt in range(30):
        try:
            fd=os.open(TTY, os.O_RDWR)
            f=open(LOG,"wb",0)
            while True:
                r,_,_=select.select([fd],[],[],1)
                if r:
                    d=os.read(fd,4096)
                    if d: f.write(d)
                else: time.sleep(0.1)
        except OSError:
            time.sleep(1); continue
    os._exit(0)

log(f"Reader PID={pid}")
open("/tmp/boot.state","w").write(f"OK\nREADER={pid}\n")
log("State saved")

# Power cycle
log("Power off")
os.system("/home/host/smartplug.py off"); time.sleep(9)
log("Power on")
os.system("/home/host/smartplug.py on")

def open_tty_retry(path, max_attempts=15):
    """Open tty device with retry — device may be a stale FIFO after USB reset."""
    for i in range(max_attempts):
        try:
            st = os.stat(path)
            if (st.st_mode & 0o170000) != 0o020000:
                time.sleep(1); continue
            fd = os.open(path, os.O_RDWR)
            return fd
        except OSError:
            time.sleep(1); continue
    raise RuntimeError(f"Could not open {path} after {max_attempts} attempts")

# Wait for port
log("Wait port")
port_ready=False
for i in range(25):
    if os.path.exists(TTY):
        try:
            if (os.stat(TTY).st_mode&0o170000)==0o020000:
                time.sleep(2); log(f"Port T+{i}s"); port_ready=True; break
        except OSError: pass
    time.sleep(1)
if not port_ready:
    log("FAIL: no port"); sys.exit(1)

# Open serial with retry
fd=open_tty_retry(TTY)
log("Port open")

# CR spam + BREAK
for _ in range(15): os.write(fd,b'\r'); time.sleep(.25)
fcntl.ioctl(fd,TIOCSBRK); time.sleep(.05); fcntl.ioctl(fd,TIOCCBRK)
time.sleep(1)

# Wait U-Boot
dl=time.time()+18
while time.time()<dl:
    r,_,_=select.select([fd],[],[],0.2)
    if r:
        d=os.read(fd,4096); t=d.decode('latin-1','replace')
        for l in t.split('\r\n'):
            if l.strip(): print(f"  {l}", flush=True)
        if '=>' in t or '# ' in t:
            log("U-Boot OK"); break
    time.sleep(.05)
else:
    log("Blind"); os.write(fd,b'\r\n'); time.sleep(1)

os.close(fd)
log("Chunk 1 DONE")
open("/tmp/boot.state","w").write(f"OK\nREADER={pid}\n")
