#!/usr/bin/env python3
"""Phase 1+2 combo: fork reader + power cycle + intercept + load + boot. ~3.5 min."""
import time, sys, os, select, fcntl

TTY="/dev/ttyACM0"; LOG="/home/host/opikernel/pvrgl-work/boot_combo.log"
KERNEL="/boot/mainline/Image"
INITRD="/boot/mainline/initrd6.19.gz"
DTB="/boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb.de-noiommu"
A="root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 modprobe.blacklist=aic8800_btlpm,aic8800_sdio console=ttyS0,115200 quiet"

TIOCSBRK = 0x5427; TIOCCBRK = 0x5428

def log(m):
    open(LOG,"a").write(f"[{time.strftime('%H:%M:%S')}] {m}\n")
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def drain(fd, timeout=0.5):
    time.sleep(timeout)
    buf=b''; dl=time.time()+timeout*3
    while time.time()<dl:
        r,_,_=select.select([fd],[],[],0.1)
        if r: buf+=os.read(fd,4096)
        else: break
    return buf

def cmd(fd, c, wait=2):
    os.write(fd, (c+"\r\n").encode())
    time.sleep(0.2)
    buf=drain(fd, wait)
    for l in buf.decode('latin-1','replace').split('\r\n'):
        if l.strip(): print(f"  {l}", flush=True)
    return buf

log("=== COMBO P1+P2 ===")

# Kill stale port holders
for pid_str in os.popen("ps aux | grep 'cat.*ttyACM\\|boot_combo\\|boot_p1\\|boot_p2' | grep -v grep | awk '{print $2}'").read().split():
    try: os.kill(int(pid_str), 9)
    except: pass
time.sleep(1)

# Fork reader
pid=os.fork()
if pid==0:
    os.setsid()
    open(LOG,"w").write("")
    fd=os.open(TTY, os.O_RDWR|os.O_NOCTTY)
    lf=open(LOG,"ab",0)
    while 1:
        r,_,_=select.select([fd],[],[],1)
        if r:
            d=os.read(fd,4096)
            lf.write(d); lf.flush()
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
        log(f"Port T+{i}s"); time.sleep(2); break
    time.sleep(1)
else:
    log("FAIL: no port"); sys.exit(1)

# Open raw
fd=os.open(TTY, os.O_RDWR|os.O_NOCTTY)
log("Port open")

# CR spam (no O_NONBLOCK so write blocks briefly, fine)
for _ in range(15): os.write(fd, b'\r'); time.sleep(.25)
# Hardware BREAK
fcntl.ioctl(fd, TIOCSBRK)
time.sleep(.05)
fcntl.ioctl(fd, TIOCCBRK)
time.sleep(1)
drain(fd, 0.5)

# Wait U-Boot
dl=time.time()+18
while time.time()<dl:
    r,_,_=select.select([fd],[],[],0.2)
    if r:
        d=os.read(fd,4096); t=d.decode('latin-1','replace')
        for l in t.split('\r\n'):
            if l.strip(): print(f"  {l}", flush=True)
        if '=> ' in t or '# ' in t:
            log("U-Boot OK"); break
else:
    log("Blind proceed"); os.write(fd, b'\r\n'); drain(fd,1)

# Disable bootcmd
log("Disabling bootcmd...")
cmd(fd, "setenv bootcmd ''", 1)
drain(fd, 0.5)

# Load kernel
log("Load kernel...")
r=cmd(fd, f"ext4load mmc 0:1 0x41000000 {KERNEL}", 15)
if b'bytes read' in r or b'Loading' in r: log("Kernel OK")
else: log("Kernel unclear")

# Load initrd
log("Load initrd...")
r=cmd(fd, f"ext4load mmc 0:1 0x43300000 {INITRD}", 30)
if b'bytes read' in r or b'Loading' in r: log("Initrd OK")
else: log("Initrd unclear")

# Load DTB
log("Load DTB...")
r=cmd(fd, f"ext4load mmc 0:1 0x43000000 {DTB}", 10)
if b'bytes read' in r or b'Loading' in r: log("DTB OK")
else: log("DTB unclear")

# fdt + bootargs
log("fdt + bootargs...")
cmd(fd, "fdt addr 0x43000000", 1)
cmd(fd, "fdt resize 65536", 1)
cmd(fd, f"setenv bootargs {A}", 2)
drain(fd, 1)

# BOOT
log("BOOTI!")
r=cmd(fd, "booti 0x41000000 - 0x43000000", 5)
drain(fd, 1)
os.close(fd)
log("BOOTING — done")
