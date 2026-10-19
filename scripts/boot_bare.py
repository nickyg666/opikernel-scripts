#!/usr/bin/env python3
"""BARE MINIMUM boot — vendor uImage only, NO DTB patching, NO fdt commands."""
import time, os, sys, fcntl, socket, select

TTY="/dev/ttyACM0"
LOG="/home/host/opikernel/pvrgl-work/boot_bare.log"
UIMAGE="/boot/uImage"
A="root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 rootwait rootfstype=ext4 modprobe.blacklist=aic8800_sdio console=ttyS0,115200 loglevel=7"
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

fcntl.ioctl(fd, TIOCSBRK); time.sleep(0.05); fcntl.ioctl(fd, TIOCCBRK)
drain(fd, 1)
for _ in range(10): os.write(fd, b'\r'); time.sleep(0.25)
drain(fd, 1)

# Disable bootcmd
log("Disable bootcmd")
os.write(fd, b"setenv bootcmd ''\r")
drain(fd, 2)

# Load uImage
log("Load uImage")
os.write(fd, f"ext4load mmc 0:1 0x41000000 {UIMAGE}\r".encode())
drain(fd, 20)

# Load DTB
log("Load DTB")
os.write(fd, "ext4load mmc 0:1 0x43000000 /boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb\r".encode())
drain(fd, 10)

# fdt addr + resize
log("fdt addr")
os.write(fd, b"fdt addr 0x43000000\r")
drain(fd, 1)
log("fdt resize")
os.write(fd, b"fdt resize 65536\r")
drain(fd, 1)
log("setenv bootargs")
os.write(fd, f"setenv bootargs {A}\r".encode())
drain(fd, 2)
log("bootm")
os.write(fd, b"bootm 0x41000000 - 0x43000000\r")
drain(fd, 3)
os.close(fd)
log("Boot sequence sent")

# Poll SSH
for i in range(36):
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