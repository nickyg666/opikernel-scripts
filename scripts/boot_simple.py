#!/usr/bin/env python3
"""Simple sequential mainline boot. No fork, no reader. Uses setsid cat background for capture."""
import time, sys, os

TTY="/dev/ttyACM0"; LOG="/home/host/opikernel/pvrgl-work/boot_simple.log"
KERNEL="/boot/mainline/Image"
INITRD="/boot/mainline/initrd6.19.gz"
DTB="/boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb.de-noiommu"
A="root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 modprobe.blacklist=aic8800_btlpm,aic8800_sdio console=ttyS0,115200 quiet"

def log(m):
    open(LOG,"a").write(f"[{time.strftime('%H:%M:%S')}] {m}\n")
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def sh(cmd, timeout=10):
    r = os.system(f"{cmd} > /dev/null 2>&1")
    return r

log("=== SIMPLE BOOT ===")

# Start background cat capture via setsid (survives parent death)
sh(f"setsid bash -c 'cat < {TTY} >> {LOG}' 2>/dev/null")
log("Capture started")
time.sleep(1)

# Power cycle
log("Power off")
sh("/home/host/smartplug.py off")
time.sleep(9)
log("Power on")
sh("/home/host/smartplug.py on")

# Wait for port
for i in range(20):
    if os.path.exists(TTY) and (os.stat(TTY).st_mode&0o170000)==0o020000:
        log(f"Port T+{i}s"); time.sleep(2); break
    time.sleep(1)
else:
    log("FAIL: no port"); sys.exit(1)

# Wait for U-Boot
time.sleep(15)
log("Assuming U-Boot prompt")

# Use cu to send commands
def cu(cmd, wait=3):
    sh(f"cu -l {TTY} -s 115200 -E '' -d -c '{cmd}' >/dev/null 2>&1 & sleep {wait}; kill %1 2>/dev/null")

# Alternative: direct echo to port
def write_cmd(c):
    with open(TTY,"wb") as f:
        f.write((c+"\r\n").encode())

# Boot sequence via direct writes
log("setenv bootcmd ''")
write_cmd("setenv bootcmd ''")
time.sleep(2)

log(f"load kernel {KERNEL}")
write_cmd(f"ext4load mmc 0:1 0x41000000 {KERNEL}")
time.sleep(20)

log(f"load initrd {INITRD}")
write_cmd(f"ext4load mmc 0:1 0x43300000 {INITRD}")
time.sleep(40)

log(f"load dtb {DTB}")
write_cmd(f"ext4load mmc 0:1 0x43000000 {DTB}")
time.sleep(5)

log("fdt addr")
write_cmd("fdt addr 0x43000000")
time.sleep(1)
log("fdt resize")
write_cmd("fdt resize 65536")
time.sleep(1)
log("setenv bootargs")
write_cmd(f"setenv bootargs {A}")
time.sleep(2)

log("BOOTI")
write_cmd("booti 0x41000000 - 0x43000000")
time.sleep(3)

log("Booting — poll SSH for 5 min...")
t0=time.time()
for i in range(30):
    time.sleep(10)
    try:
        import socket
        sk=socket.socket(); sk.settimeout(2)
        if sk.connect_ex(("192.168.0.151",22))==0:
            sk.close()
            log(f"SSH UP T+{int(time.time()-t0)}s!"); sys.exit(0)
    except: pass
    log(f"  ~{int(time.time()-t0)}s...")
log(f"FAIL T+{int(time.time()-t0)}s")
