#!/usr/bin/env python3
"""EXACT sercap_vendor_repair.log path — vendor uImage + DTB + bootm, no bootargs set."""
import time, os, sys, fcntl, socket, select

TTY="/dev/ttyACM0"
LOG="/home/host/opikernel/pvrgl-work/boot_exact.log"
TIOCSBRK=0x5427; TIOCCBRK=0x5428

def log(m):
    print(m, flush=True)
    open(LOG,"a").write(f"[{time.strftime('%H:%M:%S')}] {m}\n")

def drain(fd, t=1.0):
    time.sleep(t)

# Wait for port
for i in range(20):
    if os.path.exists(TTY) and (os.stat(TTY).st_mode&0o170000)==0o020000:
        log(f"Port T+{i}s"); break
    time.sleep(1)
else:
    log("FAIL: no port"); sys.exit(1)

for i in range(5):
    try:
        fd = os.open(TTY, os.O_RDWR); break
    except OSError:
        time.sleep(1)
else:
    log("Could not open port"); sys.exit(1)
log("Port open")
start = time.time()

# BREAK + CR spam
fcntl.ioctl(fd, TIOCSBRK); time.sleep(0.05); fcntl.ioctl(fd, TIOCCBRK)
drain(fd, 1)
for _ in range(10): os.write(fd, b'\r'); time.sleep(0.25)
drain(fd, 1)

# EXACT sercap_vendor_repair.log:
# 1. load mmc 0:1 41000000 boot/uImage
# 2. load mmc 0:1 43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb
# 3. fdt addr 43000000; fdt resize 65536
# 4. bootm 41000000 - 43000000

log("Load uImage")
os.write(fd, b"ext4load mmc 0:1 0x41000000 /boot/uImage\r")
drain(fd, 20)

log("Load DTB")
os.write(fd, b"ext4load mmc 0:1 0x43000000 /boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb\r")
drain(fd, 10)

log("fdt addr + resize")
os.write(fd, b"fdt addr 0x43000000\r")
drain(fd, 1)
os.write(fd, b"fdt resize 65536\r")
drain(fd, 1)

log("BOOTM")
os.write(fd, b"bootm 0x41000000 - 0x43000000\r")
drain(fd, 3)
os.close(fd)
log("Boot sequence sent")

# Poll SSH
for i in range(24):
    time.sleep(10)
    try:
        s=socket.socket(); s.settimeout(3)
        if s.connect_ex(("192.168.0.151",22))==0:
            s.close()
            log(f"SSH UP T+{int(time.time()-start)}s!"); sys.exit(0)
    except: pass
    if i%3==0: log(f"  ~{int(time.time()-start)}s...")

log(f"FAIL T+{int(time.time()-start)}s")
sys.exit(1)