#!/usr/bin/env python3
"""Serial boot p1-FIXED: add fdt resize before setenv bootargs.
Root cause (from p1_timed analysis):
  WARNING: could not set bootargs FDT_ERR_NOSPACE.
  ERROR: /chosen node create failed
Fix: add 'fdt addr 0x43000000 && fdt resize 65536' before 'setenv bootargs'"""
import os, time, subprocess

DEV = "/dev/ttyACM0"
LOG = "/home/host/pvrgl-work/boot_fixed.log"
PIDFILE = "/tmp/ser_fixed.pid"

def log(msg):
    ts = time.strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)

log("=== Boot p1-FIXED: fdt resize ===")

sh("pkill -f 'cat.*ttyACM' 2>/dev/null")
time.sleep(1)

log("Starting daemon reader...")
sh(f"rm -f {LOG}")
pid = os.fork()
if pid == 0:
    os.setsid()
    os.close(0); os.close(1); os.close(2)
    with open(LOG, 'wb') as out:
        with open(DEV, 'rb') as inp:
            while True:
                d = inp.read(4096)
                if d: out.write(d); out.flush()
                else: time.sleep(0.05)
    sys.exit(0)
else:
    with open(PIDFILE, 'w') as f:
        f.write(str(pid))
    time.sleep(2)
    log(f"Daemon PID={pid}")

log("Power OFF...")
sh("python3 /home/host/smartplug.py off 2>/dev/null")
time.sleep(5)
log("Power ON...")
sh("python3 /home/host/smartplug.py on 2>/dev/null")

log("Waiting for countdown...")
start = time.time()
while time.time() - start < 15:
    with open(LOG, 'rb') as f:
        text = f.read().decode('latin-1', errors='replace')
    if 'Hit any key' in text:
        log("Countdown found! Spamming...")
        for _ in range(40):
            with open(DEV, 'wb') as f:
                f.write(b'\r')
            time.sleep(0.15)
        break
    time.sleep(0.2)

time.sleep(3)
for _ in range(10):
    with open(LOG, 'rb') as f:
        text = f.read().decode('latin-1', errors='replace')
    if '=>' in text:
        log("U-Boot prompt found!")
        break
    time.sleep(0.5)

def send(cmd, delay=2):
    with open(DEV, 'wb') as f:
        f.write((cmd + '\r').encode())
    time.sleep(delay)

log("Disabling distro_bootcmd...")
send("setenv distro_bootcmd \"\"", delay=2)

bootargs = (
    "root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 rootwait rootfstype=ext4 "
    "earlyprintk=sunxi-uart,0x02500000 earlycon=uart,mmio32,0x2500000 "
    "console=ttyS0,115200 consoleblank=0 loglevel=7 clk_ignore_unused "
    "swiotlb=65536 fbcon=map:1 modprobe.blacklist=aic8800_btlpm"
)

# CORRECTED bootcmd: fdt resize AFTER loading DTB, BEFORE setting bootargs
vendor_bootcmd = (
    "ext4load mmc 0:1 0x41000000 boot/uImage && "
    "ext4load mmc 0:1 0x43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb && "
    "fdt addr 0x43000000 && fdt resize 65536 && "
    "setenv bootargs {} && bootm 0x41000000 - 0x43000000"
).format(bootargs)

log("Setting vendor bootcmd (with fdt resize)...")
send(f"setenv bootcmd \"{vendor_bootcmd}\"", delay=3)

log("Running bootcmd...")
send("run bootcmd", delay=5)

log("Waiting 30s for kernel boot...")
time.sleep(30)

sz = os.path.getsize(LOG)
log(f"Phase 1 complete. Log: {sz} bytes. EXITING cleanly.")
