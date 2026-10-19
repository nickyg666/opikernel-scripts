#!/usr/bin/env python3
"""Slower boot with long delays between commands."""
import time, os, sys, fcntl, socket, select

TTY="/dev/ttyACM0"
SCRIPT_LOG="/home/host/opikernel/pvrgl-work/boot_slow3_script.log"
READER_LOG="/home/host/opikernel/pvrgl-work/boot_slow3_reader.log"
KERNEL="/boot/mainline/Image"
INITRD="/boot/mainline/initrd.img-6.18.19+"
DTB="/boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb.orig-0810-0015"
A="root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 console=ttyS0,115200"
TIOCSBRK=0x5427; TIOCCBRK=0x5428

def log(m):
    print(m, flush=True)
    open(SCRIPT_LOG,"a").write(f"[{time.strftime('%H:%M:%S')}] {m}\n")

def send(fd, cmd, wait=3.0):
    """Send command and wait."""
    os.write(fd, (cmd+"\r").encode())
    time.sleep(wait)
    return cmd

log("=== SLOW BOOT ===")
start = time.time()

# Fork reader
pid = os.fork()
if pid == 0:
    os.setsid()
    fd = os.open(TTY, os.O_RDWR)
    lf = open(READER_LOG, "wb", 0)
    while True:
        r,_,_ = select.select([fd],[],[],1)
        if r:
            d = os.read(fd, 4096)
            if d: lf.write(d)
        else:
            time.sleep(0.1)
    os._exit(0)

log(f"Reader PID={pid}")
open(READER_LOG,"wb").write(b"")
time.sleep(1)

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
time.sleep(2)

# CR spam
for _ in range(10): os.write(fd, b'\r'); time.sleep(0.25)
time.sleep(1)

# === BOOT SEQUENCE WITH LONG DELAYS ===
log("1. Disable bootcmd")
send(fd, "setenv bootcmd ''", wait=3)

log("2. Load kernel (26MB)")
send(fd, f"ext4load mmc 0:1 0x41000000 {KERNEL}", wait=20)

log("3. Load initrd (34MB)")
send(fd, f"ext4load mmc 0:1 0x43300000 {INITRD}", wait=30)

log("4. Load DTB")
send(fd, f"ext4load mmc 0:1 0x43000000 {DTB}", wait=10)

log("5. fdt addr")
send(fd, "fdt addr 0x43000000", wait=2)

log("6. fdt resize")
send(fd, "fdt resize 65536", wait=2)

log("7. setenv bootargs")
send(fd, f"setenv bootargs {A}", wait=2)

log("8. BOOTI")
send(fd, "booti 0x41000000 - 0x43000000", wait=3)

os.close(fd)
log("Boot sequence sent")

# Poll SSH
for i in range(30):
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