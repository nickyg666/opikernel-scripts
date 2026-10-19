#!/usr/bin/env python3
"""Serial boot p1-MINIMAL: no custom bootargs, just boot vendor kernel.
Root cause chain: setenv truncates (char-drop) → FDT_ERR_NOSPACE (packed DTB) → panic.
Fix: boot with vendor defaults, fix blacklist via SSH from userspace."""
import os, sys, time, subprocess

DEV = "/dev/ttyACM0"
LOG = "/home/host/pvrgl-work/boot_minimal.log"
PIDFILE = "/tmp/ser_minimal.pid"

def log(msg):
    ts = time.strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)

log("=== Boot p1-MINIMAL: vendor defaults ===")

sh("pkill -f 'cat.*ttyACM' 2>/dev/null")
time.sleep(1)

log("Starting daemon reader...")
sh(f"rm -f {LOG}")
pid = os.fork()
if pid == 0:
    os.setsid()
    os.close(0); os.close(1); os.close(2)
    with open(DEV, 'rb') as inp:
        with open(LOG, 'wb') as out:
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

# Disable distro_bootcmd (the villain!)
log("Disabling distro_bootcmd...")
send("setenv distro_bootcmd \"\"", delay=2)

# Bootcmd with MINIMAL bootargs — just console redirection
# Vendor kernel uses its built-in initrd's bootargs (including correct root=)
minimal_bootcmd = (
    "ext4load mmc 0:1 0x41000000 boot/uImage && "
    "ext4load mmc 0:1 0x43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb && "
    "setenv bootargs console=ttyS0,115200 && "
    "bootm 0x41000000 - 0x43000000"
)

log("Setting minimal bootcmd (vendor defaults for root=)...")
send(f"setenv bootcmd \"{minimal_bootcmd}\"", delay=3)

log("Running bootcmd...")
send("run bootcmd", delay=5)

# Wait 30s for kernel to boot, then exit cleanly
log("Waiting 30s for kernel boot, then exiting...")
time.sleep(30)

sz = os.path.getsize(LOG)
log(f"Phase 1 complete. Log: {sz} bytes. EXITING.")
