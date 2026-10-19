#!/usr/bin/env python3
"""Serial boot v7: disable old bootcmd BEFORE it auto-runs.
Root cause: old boot.scr's bootcmd runs a 2nd time after kernel starts,
overwriting kernel's DTB at 0x43000000 → kernel panic.
Fix: setenv bootcmd "" before bootcmd fires.
"""
import os, time, subprocess

DEV = "/dev/ttyACM0"
LOG = "/home/host/pvrgl-work/boot_v7.log"
PIDFILE = "/tmp/ser_v7.pid"

def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG + ".txt", 'a') as f:
        f.write(line + '\n')

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)

log("=== Serial boot v7: disable bootcmd ===")

# Kill existing cats
sh("pkill -f 'cat.*ttyACM' 2>/dev/null")
time.sleep(1)

# Start forked daemon reader
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
    log(f"Daemon PID={pid}")
    time.sleep(2)
    log(f"Daemon alive: {sh(f'ps -p {pid} -o pid 2>/dev/null && echo YES || echo NO').stdout.strip()}")

# Power cycle
log("Power OFF...")
sh("python3 /home/host/smartplug.py off 2>/dev/null")
time.sleep(5)
log("Power ON...")
sh("python3 /home/host/smartplug.py on 2>/dev/null")
log("Waiting 10s for U-Boot...")
time.sleep(10)

sz0 = os.path.getsize(LOG)
log(f"Log: {sz0} bytes")

# Enter spam during autoboot — intercept before first bootcmd fires
log("Enter spam (40x) to catch U-Boot...")
for _ in range(40):
    with open(DEV, 'wb') as f:
        f.write(b'\r')
    time.sleep(0.25)
time.sleep(2)

# Check for U-Boot
with open(LOG, 'rb') as f:
    text = f.read().decode('latin-1', errors='replace')

if '=>' in text or 'Hit any' in text:
    log("U-Boot prompt intercepted!")
else:
    log("No prompt — waiting more...")
    time.sleep(5)
    with open(LOG, 'rb') as f:
        text = f.read().decode('latin-1', errors='replace')

def send(cmd, delay=2):
    with open(DEV, 'wb') as f:
        f.write((cmd + '\r').encode())
    time.sleep(delay)

# CRITICAL STEP: disable old bootcmd BEFORE it fires
# Old bootcmd: load boot/mainline/Image + bootm → overwrites kernel + DTB
log("DISABLING old bootcmd...")
send("setenv bootcmd", delay=3)  # Show current bootcmd first
send("setenv bootcmd \"\"", delay=3)  # Disable it
send("setenv bootdelay -1", delay=2)  # No autoboot

# Now set OUR bootargs
bootargs = (
    "root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 rootwait rootfstype=ext4 "
    "earlyprintk=sunxi-uart,0x02500000 earlycon=uart,mmio32,0x2500000 "
    "console=ttyS0,115200 consoleblank=0 loglevel=7 clk_ignore_unused "
    "swiotlb=65536 fbcon=map:1 modprobe.blacklist=aic8800_btlpm"
)
log(f"Setting bootargs (modprobe.blacklist=aic8800_btlpm)...")
send(f"setenv bootargs {bootargs}", delay=2)

# Load vendor kernel + DTB
log("Loading vendor uImage @ 0x41000000...")
send("ext4load mmc 0:1 0x41000000 boot/uImage", delay=15)

log("Loading vendor DTB @ 0x43000000...")
send("ext4load mmc 0:1 0x43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb", delay=5)

# Boot with OUR bootargs (NO initrd — vendor uImage has built-in)
log("Booting with bootm (NO initrd)...")
send("bootm 0x41000000 - 0x43000000", delay=5)

log("Kernel boot in progress — monitoring for 120s...")
time.sleep(30)
sz1 = os.path.getsize(LOG)
log(f"Log: {sz0} -> {sz1} bytes (+{sz1-sz0})")

time.sleep(30)
sz2 = os.path.getsize(LOG)
log(f"Log: {sz1} -> {sz2} bytes (+{sz2-sz1})")

time.sleep(60)
sz3 = os.path.getsize(LOG)
log(f"Log: {sz2} -> {sz3} bytes (+{sz3-sz2})")

log("=== FINAL STATE ===")
log(f"Daemon alive: {sh(f'ps -p {pid} -o pid 2>/dev/null && echo YES || echo NO').stdout.strip()}")
log(f"Log grew: {sz0} -> {sz3} (+{sz3-sz0})")

# SSH check
r = subprocess.run(
    ["sshpass", "-p", "orangepi", "ssh", "-o", "StrictHostKeyChecking=accept-new",
     "-o", "ConnectTimeout=5", "orangepi@192.168.0.151", "uptime"],
    capture_output=True, text=True, timeout=10
)
if r.returncode == 0:
    log(f"BOARD ONLINE: {r.stdout.strip()}")
else:
    log("Board not yet reachable")
    with open(LOG, 'rb') as f:
        data = f.read()
    text = data.decode('latin-1', errors='replace')
    import re
    chunks = re.findall(r'[\x20-\x7e]{6,}', text)
    for m in ["login:", "Starting kernel", "EXT4", "aic8800", "root@", "Kernel panic", "VFS:", "CPU:", "=>"]:
        hits = [c for c in chunks if m in c]
        if hits:
            log(f"  '{m}' found ({len(hits)} times): {hits[-1][:150]}")

log("=== DONE ===")
