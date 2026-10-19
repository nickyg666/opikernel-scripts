#!/usr/bin/env python3
"""Complete mainline boot with SSH polling."""
import time, os, sys, fcntl, select, socket

TTY="/dev/ttyACM0"; LOG="/home/host/opikernel/pvrgl-work/boot_complete3.log"
KERNEL="/boot/mainline/Image"
INITRD="/boot/mainline/initrd6.19.gz"
DTB="/boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb"
A="root=/dev/mmcblk1p1 rootdelay=5 console=ttyS0,115200 earlyprintk loglevel=7 ignore_loglevel"
TIOCSBRK=0x5427; TIOCCBRK=0x5428

def log(m):
    print(m, flush=True)
    open(LOG,"a").write(f"[{time.strftime('%H:%M:%S')}] {m}\n")

def drain(fd, secs=1.0):
    time.sleep(secs)

# Fork reader
pid = os.fork()
if pid == 0:
    os.setsid()
    fd = os.open(TTY, os.O_RDWR)
    lf = open(LOG, "wb", 0)
    while True:
        r,_,_ = select.select([fd],[],[],1)
        if r:
            d = os.read(fd, 4096)
            if d: lf.write(d)
        else:
            time.sleep(0.1)
    os._exit(0)

log(f"Reader PID={pid}")
start = time.time()
log("=== COMPLETE BOOT ===")

# Open port
for i in range(5):
    try:
        fd = os.open(TTY, os.O_RDWR); break
    except OSError:
        time.sleep(1)
else:
    log("Could not open port"); sys.exit(1)
log("Port open")

# Hardware BREAK + CR spam
fcntl.ioctl(fd, TIOCSBRK); time.sleep(0.05); fcntl.ioctl(fd, TIOCCBRK)
drain(fd, 1)
for _ in range(10): os.write(fd, b'\r'); time.sleep(0.25)
drain(fd, 0.5)

# Disable bootcmd
os.write(fd, b"setenv bootcmd ''\r")
drain(fd, 2)

# Load kernel
os.write(fd, f"ext4load mmc 0:1 0x41000000 {KERNEL}\r".encode())
drain(fd, 20)

# Load initrd
os.write(fd, f"ext4load mmc 0:1 0x43300000 {INITRD}\r".encode())
drain(fd, 30)

# Load DTB
os.write(fd, f"ext4load mmc 0:1 0x43000000 {DTB}\r".encode())
drain(fd, 10)

# fdt + bootargs
os.write(fd, b"fdt addr 0x43000000\r"); drain(fd, 1)
os.write(fd, b"fdt resize 65536\r"); drain(fd, 1)
os.write(fd, f"setenv bootargs {A}\r".encode()); drain(fd, 2)

# BOOT
os.write(fd, b"booti 0x41000000 - 0x43000000\r")
drain(fd, 3)
os.close(fd)
log("Boot sequence sent")

# Poll SSH for 5 min
for i in range(30):
    time.sleep(10)
    try:
        s=socket.socket(); s.settimeout(3)
        if s.connect_ex(("192.168.0.151",22))==0:
            s.close()
            log(f"SSH UP T+{int(time.time()-start)}s!")
            sys.exit(0)
    except: pass
    log(f"  ~{int(time.time()-start)}s...")

log("FAIL: SSH timeout")
sys.exit(1)