#!/usr/bin/env python3
"""Chunk 2: Load kernel + initrd + DTB + booti. NO blocking serial reads.
Uses timed sleeps instead of select.select (which blocks and triggers SIGKILL).
"""
import time, os, sys, fcntl

TTY="/dev/ttyACM0"; LOG="/home/host/opikernel/pvrgl-work/boot_c2.log"
STATE="/tmp/boot.state"
KERNEL="/boot/mainline/Image"
INITRD="/boot/mainline/initrd6.19.gz"
DTB="/boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb"
A="root=/dev/mmcblk1p1 rootdelay=5 console=ttyS0,115200 init=/init"
TIOCSBRK=0x5427; TIOCCBRK=0x5428

def log(m):
    print(m, flush=True)
    open(LOG,"a").write(f"[{time.strftime('%H:%M:%S')}] {m}\n")

def drain(fd, secs=1.0):
    """Drain serial by sleeping (no select)."""
    time.sleep(secs)

# Verify state
st=open(STATE).read() if os.path.exists(STATE) else ""
if 'OK' not in st and 'BOOTING' not in st:
    log(f"State invalid: {st!r}"); sys.exit(1)
log("=== CHUNK 2: Boot ===")

# Open port
for i in range(5):
    try:
        fd=os.open(TTY, os.O_RDWR); break
    except OSError:
        time.sleep(1)
else:
    log("Could not open port"); sys.exit(1)
log("Port open")

# Drain stale
drain(fd, 0.5)

# Hardware BREAK to drop to shell
fcntl.ioctl(fd, TIOCSBRK); time.sleep(0.05); fcntl.ioctl(fd, TIOCCBRK)
drain(fd, 1.0)

# CR to clear
os.write(fd, b'\r')
drain(fd, 0.5)

# === 1. Disable bootcmd ===
log("Disabling bootcmd...")
os.write(fd, b"setenv bootcmd ''\r")
drain(fd, 2.0)

# === 2. Load kernel (26MB) ===
log("Load kernel...")
os.write(fd, f"ext4load mmc 0:1 0x41000000 {KERNEL}\r".encode())
drain(fd, 20.0)  # ~2s for 26MB, allow 20s

# === 3. Load initrd (34MB) ===
log("Load initrd...")
os.write(fd, f"ext4load mmc 0:1 0x43300000 {INITRD}\r".encode())
drain(fd, 30.0)  # ~2s for 34MB, allow 30s

# === 4. Load DTB ===
log("Load DTB...")
os.write(fd, f"ext4load mmc 0:1 0x43000000 {DTB}\r".encode())
drain(fd, 10.0)

# === 5. fdt + bootargs ===
log("fdt addr...")
os.write(fd, b"fdt addr 0x43000000\r")
drain(fd, 1.0)
log("fdt resize...")
os.write(fd, b"fdt resize 65536\r")
drain(fd, 1.0)
log("setenv bootargs...")
os.write(fd, f"setenv bootargs {A}\r".encode())
drain(fd, 2.0)

# === 6. BOOT ===
log("BOOTI!")
os.write(fd, b"booti 0x41000000 - 0x43000000\r")
drain(fd, 3.0)

os.close(fd)
log("BOOTING")
open(STATE,"w").write("BOOTING\n")
