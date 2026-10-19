#!/usr/bin/env python3
"""Phase 2: Raw os.open (reader holds port), load + boot."""
import time, sys, os, select

TTY="/dev/ttyACM0"; BAUD=115200
LOG="/home/host/opikernel/pvrgl-work/boot_p2.log"
KERNEL="/boot/mainline/Image"
INITRD="/boot/mainline/initrd6.19.gz"
DTB="/boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb.de-noiommu"
A="root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 modprobe.blacklist=aic8800_btlpm,aic8800_sdio console=ttyS0,115200 quiet"

def log(m):
    open(LOG,"w").write(f"[{time.strftime('%H:%M:%S')}] {m}\n")
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def drain(fd, timeout=0.5):
    """Read all available data."""
    time.sleep(timeout)
    buf=b''
    dl=time.time()+timeout*3
    while time.time()<dl:
        r,_,_=select.select([fd],[],[],0.1)
        if r: buf+=os.read(fd,4096)
        else: break
    return buf

def cmd(fd, c, wait=2):
    """Send command, drain response."""
    os.write(fd, (c+"\r\n").encode())
    time.sleep(0.2)
    buf=drain(fd, wait)
    t=buf.decode('latin-1','replace')
    for l in t.split('\r\n'):
        if l.strip(): print(f"  {l}", flush=True)
    return buf

log("=== P2: Load + boot ===")

# Open port raw (reader also has it open — OS allows multiple readers)
try:
    fd=os.open(TTY, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    log("Port open (raw)")
except Exception as e:
    log(f"Port open FAIL: {e}"); sys.exit(1)

# Drain stale
drain(fd, 0.5)

# Check U-Boot prompt
buf=cmd(fd, "", 2)
t=buf.decode('latin-1','replace')
if '=> ' in t or '# ' in t:
    log("U-Boot OK")
else:
    log("WARNING: no U-Boot prompt")

# Disable distro_bootcmd
log("Disabling bootcmd...")
cmd(fd, "setenv bootcmd ''", 1)

# Load kernel (26MB)
log(f"Load kernel {KERNEL}...")
r=cmd(fd, f"ext4load mmc 0:1 0x41000000 {KERNEL}", 15)
if b'bytes read' in r or b'Loading' in r: log("Kernel OK")
else: log("WARNING: kernel unclear")

# Load initrd (34MB)
log(f"Load initrd {INITRD}...")
r=cmd(fd, f"ext4load mmc 0:1 0x43300000 {INITRD}", 30)
if b'bytes read' in r or b'Loading' in r: log("Initrd OK")
else: log("WARNING: initrd unclear")

# Load DTB
log(f"Load DTB {DTB}...")
r=cmd(fd, f"ext4load mmc 0:1 0x43000000 {DTB}", 10)
if b'bytes read' in r or b'Loading' in r: log("DTB OK")
else: log("WARNING: DTB unclear")

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
log("Phase 2 DONE")
open("/tmp/boot_p1.state","w").write("BOOTING\n")
