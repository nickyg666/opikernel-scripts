#!/usr/bin/env python3
"""Boot with persistent reader. Reader runs in BACKGROUND, parent boots, polls SSH."""
import time, os, sys, fcntl, select, socket, subprocess

TTY="/dev/ttyACM0"; LOG="/home/host/opikernel/pvrgl-work/boot_persist.log"
KERNEL="/boot/mainline/Image"
INITRD="/boot/mainline/initrd6.19.gz"
DTB="/boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb"
A="root=/dev/mmcblk1p1 rootdelay=5 console=ttyS0,115200 earlyprintk loglevel=7"
TIOCSBRK=0x5427; TIOCCBRK=0x5428

def log(m):
    print(m, flush=True)
    open(LOG,"a").write(f"[{time.strftime('%H:%M:%S')}] {m}\n")

# Start persistent reader via setsid background (survives parent)
reader_cmd = f"setsid cat < {TTY} >> {LOG} >/dev/null 2>&1"
log(f"Starting reader: {reader_cmd}")
os.system(f"{reader_cmd} &")
time.sleep(2)
log("Reader should be running in background")

log("=== PERSISTENT BOOT ===")
start = time.time()

# Open port
for i in range(10):
    try:
        fd = os.open(TTY, os.O_RDWR); break
    except OSError:
        time.sleep(1)
else:
    log("Could not open port"); sys.exit(1)
log("Port open")

# Hardware BREAK
fcntl.ioctl(fd, TIOCSBRK); time.sleep(0.05); fcntl.ioctl(fd, TIOCCBRK)
time.sleep(1)

# CR spam
for _ in range(10): os.write(fd, b'\r'); time.sleep(0.25)
time.sleep(0.5)

# Disable bootcmd
os.write(fd, b"setenv bootcmd ''\r")
time.sleep(2)

# Load kernel
log("Load kernel")
os.write(fd, f"ext4load mmc 0:1 0x41000000 {KERNEL}\r".encode())
time.sleep(20)

# Load initrd
log("Load initrd")
os.write(fd, f"ext4load mmc 0:1 0x43300000 {INITRD}\r".encode())
time.sleep(30)

# Load DTB
log("Load DTB")
os.write(fd, f"ext4load mmc 0:1 0x43000000 {DTB}\r".encode())
time.sleep(10)

# fdt + bootargs
os.write(fd, b"fdt addr 0x43000000\r"); time.sleep(1)
os.write(fd, b"fdt resize 65536\r"); time.sleep(1)
os.write(fd, f"setenv bootargs {A}\r".encode()); time.sleep(2)

# BOOT
log("BOOTI")
os.write(fd, b"booti 0x41000000 - 0x43000000\r")
time.sleep(3)
os.close(fd)
log("Boot sequence sent")

# Poll SSH (8 min, longer wait)
for i in range(48):
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