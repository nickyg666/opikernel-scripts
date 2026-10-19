#!/usr/bin/env python3
"""Clean boot: reader and boot scripts use different files."""
import time, os, sys, fcntl, socket, select

TTY="/dev/ttyACM0"
SCRIPT_LOG="/home/host/opikernel/pvrgl-work/boot_script.log"
READER_LOG="/home/host/opikernel/pvrgl-work/boot_reader.log"
KERNEL="/boot/mainline/Image"
INITRD="/boot/mainline/initrd6.19.gz"
DTB="/boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb"
A="root=/dev/mmcblk1p1 rootdelay=5 console=ttyS0,115200 earlyprintk loglevel=7"
TIOCSBRK=0x5427; TIOCCBRK=0x5428

def log(m):
    print(m, flush=True)
    open(SCRIPT_LOG,"a").write(f"[{time.strftime('%H:%M:%S')}] {m}\n")

log("=== CLEAN BOOT ===")
start = time.time()

# Open fresh reader in a separate process via fork
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
# Clear old reader log
open(READER_LOG,"wb").write(b"")
time.sleep(1)

# Open port for sending
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
time.sleep(15)

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